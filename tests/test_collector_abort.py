"""The collectors must stop when their source goes away mid-run.

Both bounds regression-test the 2026-09-01 outage. mt5-test was OOM-killed
partway through a D3b pull; the probe at the top of the run had already
succeeded, so neither collector's start-up check was in a position to notice.
D3b then attempted 7 symbols x 72 chunks against a refused socket, and D3a ran
for five days writing 65,228 error rows against 976 usable samples while its
line count and process liveness both looked healthy.

The start-up probe covers "dead before we began". These cover "died while we
were reading", which is the case that actually occurred.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


class _DyingHandler(BaseHTTPRequestHandler):
    """Answers the probe, serves ``ok_calls`` data requests, then fails."""

    ok_calls = 0
    calls = 0

    def log_message(self, *args) -> None:  # noqa: ANN002 — silence the server
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, {"success": "true", "description": {
                "mt5_connected": "True", "status": "running"}})
            return

        type(self).calls += 1
        if type(self).calls > type(self).ok_calls:
            # 503 maps to MT5Unavailable in _client.get(), which is the same
            # class the refused socket produced during the real outage.
            self._send(503, {"detail": "terminal gone"})
            return
        self._send(200, self._data())

    def _data(self) -> dict:
        if self.path.startswith("/api/v1/ticks"):
            return {"ticks": [], "count": 0}
        return {"bid": 1.1, "ask": 1.1001, "time": "2026-09-01T00:00:00"}

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def dying_server():
    def _start(ok_calls: int) -> str:
        handler = type("H", (_DyingHandler,), {"ok_calls": ok_calls, "calls": 0})
        srv = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _start.servers.append(srv)
        return f"http://127.0.0.1:{srv.server_port}"

    _start.servers = []
    yield _start
    for srv in _start.servers:
        srv.shutdown()


def _run(module: str, url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=REPO, capture_output=True, text=True, timeout=180,
        env={"PATH": "/usr/bin:/bin", "MT5_API_URL": url,
             "PYTHONPATH": str(REPO)},
    )


def test_d3a_aborts_when_every_symbol_stops_answering(dying_server, tmp_path):
    url = dying_server(ok_calls=2)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--max-consecutive-failures", "3",
                "--symbols", "EURUSD", "--out", str(out))

    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout[proc.stdout.index("{", proc.stdout.index("}")):])
    assert summary["aborted_source_unreachable"] is True
    assert summary["consecutive_dead_rounds_at_exit"] == 3

    # The bound is the point: a handful of rows, not five days of them.
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) < 10
    assert any(r.get("ok") is False for r in rows)


def test_d3a_resets_the_counter_on_a_good_round(dying_server, tmp_path):
    """A transient hole must not accumulate toward the abort threshold."""
    url = dying_server(ok_calls=10_000)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once",
                "--symbols", "EURUSD", "--out", str(out))

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout[proc.stdout.index("{", proc.stdout.index("}")):])
    assert summary["aborted_source_unreachable"] is False
    assert summary["consecutive_dead_rounds_at_exit"] == 0


def test_d3b_aborts_mid_run_and_records_unattempted_symbols(dying_server, tmp_path):
    url = dying_server(ok_calls=1)

    proc = _run("phase0.collectors.d3b_spread_history", url,
                "--months", "1", "--chunk-days", "5",
                "--max-consecutive-failures", "3",
                "--symbols", "EURUSD", "GBPUSD", "USDJPY",
                "--out-dir", str(tmp_path))

    assert proc.returncode == 2, proc.stderr + proc.stdout
    artifact = json.loads(sorted(tmp_path.glob("d3b_*.json"))[-1].read_text())

    assert artifact["status"] == "ABORTED_SOURCE_UNREACHABLE"
    assert "consecutive chunks" in artifact["aborted_reason"]

    # Symbols after the abort are marked not-attempted rather than silently
    # absent, so obtained coverage cannot later be read as broker behaviour.
    assert "not attempted" in artifact["errors"]["GBPUSD"]
    assert "not attempted" in artifact["errors"]["USDJPY"]
