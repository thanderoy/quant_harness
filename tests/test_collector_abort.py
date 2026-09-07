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
import re
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
    tick_time = "2026-09-01T00:00:00"
    # Serve `tick_time` for the first `switch_after` data calls, then
    # `tick_time_after`. Offset detection reads the freshest tick before
    # sampling begins, so a test needs a fresh tick during detection and a
    # stale one during sampling — the same sequence a real open market gives.
    tick_time_after = None
    switch_after = 0

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
        if self.path.startswith("/api/v1/account"):
            return {"server": "PepperstoneKE-MT5-Live01", "trade_mode": 0,
                    "currency": "USD", "login": 123, "name": "someone"}
        tt = self.tick_time
        if self.tick_time_after and type(self).calls > self.switch_after:
            tt = self.tick_time_after
        return {"bid": 1.1, "ask": 1.1001, "time": tt}

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def dying_server():
    def _start(ok_calls: int, tick_time: str | None = None,
               tick_time_after: str | None = None,
               switch_after: int = 0) -> str:
        handler = type("H", (_DyingHandler,),
                       {"ok_calls": ok_calls, "calls": 0,
                        "tick_time": tick_time or _DyingHandler.tick_time,
                        "tick_time_after": tick_time_after,
                        "switch_after": switch_after})
        srv = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _start.servers.append(srv)
        return f"http://127.0.0.1:{srv.server_port}"

    _start.servers = []
    yield _start
    for srv in _start.servers:
        srv.shutdown()


def _last_json(stdout: str) -> dict:
    """Parse the final JSON object printed to stdout.

    The collector prints a start-up line, optionally a schedule line, then the
    run summary. Locating the summary by counting braces broke the moment a
    line was added ahead of it, so decode from the end instead.
    """
    dec = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"^\{", stdout, re.MULTILINE)]
    assert starts, f"no JSON object in stdout: {stdout!r}"
    obj, _ = dec.raw_decode(stdout[starts[-1]:])
    return obj


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
    summary = _last_json(proc.stdout)
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
    summary = _last_json(proc.stdout)
    assert summary["aborted_source_unreachable"] is False
    assert summary["consecutive_dead_rounds_at_exit"] == 0


def test_d3b_aborts_mid_run_and_records_unattempted_symbols(dying_server, tmp_path):
    url = dying_server(ok_calls=1)

    proc = _run("phase0.collectors.d3b_spread_history", url,
                "--months", "1", "--chunk-days", "5",
                "--max-consecutive-failures", "3", "--retry-backoff-base", "0",
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


def test_d3a_stamps_the_trade_server_on_every_row(dying_server, tmp_path):
    """The mislabel that voided the 2026-09-01 runs must not be repeatable."""
    url = dying_server(ok_calls=10_000)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once",
                "--symbols", "EURUSD", "GBPUSD", "--out", str(out))

    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows and all(r["server"] == "PepperstoneKE-MT5-Live01" for r in rows)

    # Account identity is deliberately not collected.
    assert not any("login" in r or "name" in r for r in rows)


def test_d3a_refuses_a_server_that_does_not_match(dying_server, tmp_path):
    url = dying_server(ok_calls=10_000)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once", "--symbols", "EURUSD",
                "--expect-server", "MetaQuotes", "--out", str(out))

    assert proc.returncode == 3, proc.stdout
    assert "does not match" in proc.stderr
    assert not out.exists()


def test_d3a_flags_a_stale_tick(dying_server, tmp_path):
    """A closed market returns the same last tick every round.

    Nine symbols a minute across a weekend is ~26,000 identical rows, each
    carrying the wide at-the-close spread. Recorded, but flagged, so they
    cannot dominate a median computed over the file.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    fresh = now.replace(tzinfo=None).isoformat()
    old_tick = (now - timedelta(hours=2)).replace(tzinfo=None).isoformat()

    # Fresh while the collector establishes context, stale once sampling
    # starts. Three calls precede the first sample: /api/v1/account for the
    # broker stamp, the warm-up touch, and offset detection.
    url = dying_server(ok_calls=10_000, tick_time=fresh,
                       tick_time_after=old_tick, switch_after=3)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once", "--symbols", "EURUSD",
                "--out", str(out))

    assert proc.returncode == 0, proc.stderr
    row = json.loads(out.read_text().splitlines()[0])
    assert row["server_utc_offset_hours"] == 0
    assert row["stale"] is True
    assert row["tick_age_s"] > 300
    # Flagged, never dropped: the spread is still recorded.
    assert row["spread"] > 0


def test_d3a_does_not_flag_a_fresh_tick(dying_server, tmp_path):
    from datetime import datetime, timezone
    fresh = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    url = dying_server(ok_calls=10_000, tick_time=fresh)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once", "--symbols", "EURUSD",
                "--out", str(out))

    assert proc.returncode == 0, proc.stderr
    row = json.loads(out.read_text().splitlines()[0])
    assert row["stale"] is False


def test_d1_refuses_a_server_mismatch(dying_server, tmp_path):
    """Contract specs are broker policy; an unlabelled dump is uninterpretable."""
    url = dying_server(ok_calls=10_000)

    proc = _run("phase0.collectors.d1_contract_specs", url,
                "--out-dir", str(tmp_path), "--expect-server", "MetaQuotes")

    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "does not match" in proc.stderr


def test_d3b_refuses_a_server_mismatch(dying_server, tmp_path):
    url = dying_server(ok_calls=10_000)

    proc = _run("phase0.collectors.d3b_spread_history", url,
                "--months", "1", "--out-dir", str(tmp_path),
                "--expect-server", "MetaQuotes")

    assert proc.returncode == 4, proc.stdout + proc.stderr
    artifact = json.loads(sorted(tmp_path.glob("d3b_*.json"))[-1].read_text())
    assert artifact["status"] == "REFUSED_SERVER_MISMATCH"
    assert artifact["broker"]["server"] == "PepperstoneKE-MT5-Live01"


def test_d3b_counts_zero_spreads_and_excludes_only_crossed():
    """A zero spread is a genuine raw-feed quote; a crossed one is impossible.

    Measured on PepperstoneKE-MT5-Live01: EURUSD quotes exactly 0.0 on 86% of
    ticks with none crossed, while XAUUSD has none at all. Excluding the zeros
    discarded most of the real distribution and reported a median of 1e-05 for
    a pair whose true median spread is 0.0.
    """
    from phase0.collectors.d3b_spread_history import SymbolAccumulator

    acc = SymbolAccumulator()
    acc.add([
        {"time": "2026-09-04T13:00:00Z", "bid": 1.16170, "ask": 1.16170},  # zero
        {"time": "2026-09-04T13:00:01Z", "bid": 1.16170, "ask": 1.16170},  # zero
        {"time": "2026-09-04T13:00:02Z", "bid": 1.16170, "ask": 1.16171},  # 1pt
        {"time": "2026-09-04T13:00:03Z", "bid": 1.16172, "ask": 1.16170},  # crossed
    ], truncated=False)

    r = acc.result()
    assert r["n_zero_spreads_included"] == 2
    assert r["n_crossed_spreads_excluded"] == 1
    assert r["overall"]["n"] == 3          # zeros are in the distribution
    assert r["overall"]["median_spread"] == 0.0
    assert r["zero_spread_fraction"] == 0.5


def test_d3b_artifact_names_what_is_outstanding(dying_server, tmp_path):
    """A killed run must not leave an artifact that reads as still-running.

    The 2026-09-06 run was SIGKILLed on XAUUSD with seven symbols complete and
    left status IN_PROGRESS, which is indistinguishable from a run still being
    written. The process gets no chance to record its own death, so the
    incremental write has to name what is outstanding.
    """
    url = dying_server(ok_calls=1)

    proc = _run("phase0.collectors.d3b_spread_history", url,
                "--months", "1", "--chunk-days", "5",
                "--max-consecutive-failures", "2", "--retry-backoff-base", "0",
                "--symbols", "EURUSD", "GBPUSD", "--out-dir", str(tmp_path))

    assert proc.returncode == 2, proc.stdout + proc.stderr
    artifact = json.loads(sorted(tmp_path.glob("d3b_*.json"))[-1].read_text())
    assert artifact["symbols_requested"] == ["EURUSD", "GBPUSD"]
    assert artifact["symbols_remaining"] == ["EURUSD", "GBPUSD"]
    assert artifact["updated_at_utc"]


def test_next_boundary_lands_just_after_the_bar_close():
    """The entry-conditional estimator is only meaningful at the boundary.

    R7: a strategy acting on a closed H1 bar pays the spread at HH:00:00 plus
    its own wake/fetch/decide latency, and never the spread at an arbitrary
    moment. Sampling has to hit that instant, not the nearest convenient one.
    """
    from datetime import datetime, timezone
    from phase0.collectors.d3a_spread_forward import (
        next_boundary, TIMEFRAME_SECONDS,
    )

    now = datetime(2026, 9, 7, 10, 17, 33, tzinfo=timezone.utc)

    h1 = next_boundary(now, TIMEFRAME_SECONDS["H1"], 0.75)
    assert (h1.hour, h1.minute, h1.second) == (11, 0, 0)
    assert h1.microsecond == 750_000

    m15 = next_boundary(now, TIMEFRAME_SECONDS["M15"], 0.75)
    assert (m15.hour, m15.minute, m15.second) == (10, 30, 0)

    # Immediately after a boundary fires, the next one is a full period away
    # rather than the same instant again.
    after = next_boundary(h1, TIMEFRAME_SECONDS["H1"], 0.75)
    assert (after - h1).total_seconds() == 3600


def test_d3a_labels_the_schedule_that_produced_each_row(dying_server, tmp_path):
    """Time-weighted and entry-conditional samples must not be poolable."""
    url = dying_server(ok_calls=10_000)
    out = tmp_path / "samples.jsonl"

    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once", "--symbols", "EURUSD",
                "--out", str(out))

    assert proc.returncode == 0, proc.stderr
    row = json.loads(out.read_text().splitlines()[0])
    assert row["sample_kind"] == "periodic"
    assert row["bar_timeframe"] is None


def test_tick_age_uses_the_broker_offset():
    """Broker tick timestamps are naive SERVER time, not UTC.

    Treating them as UTC understated every age by the offset. On Pepperstone
    (UTC+3) a tick 750ms old reported tick_age_s of -10799, which left `stale`
    unable to fire until a tick was more than three hours out of date.
    """
    from datetime import datetime, timezone
    from phase0.collectors.d3a_spread_forward import tick_age_seconds, _is_stale

    sampled = datetime(2026, 9, 7, 9, 15, 0, 750000, tzinfo=timezone.utc)

    # Server is UTC+3, so 12:15:00 server == 09:15:00 UTC: a 0.75s old tick.
    age = tick_age_seconds("2026-09-07T12:15:00", sampled, 3)
    assert abs(age - 0.75) < 0.01
    assert _is_stale(age) is False

    # The old behaviour, for contrast.
    assert tick_age_seconds("2026-09-07T12:15:00", sampled, 0) < -10_000

    # A genuinely stale tick still trips, now at the right threshold.
    assert _is_stale(tick_age_seconds("2026-09-07T11:15:00", sampled, 3)) is True

    # Unknown offset yields an unknown age, not a confident wrong one, and
    # `stale` is None rather than False — False would assert freshness.
    assert tick_age_seconds("2026-09-07T12:15:00", sampled, None) is None
    assert _is_stale(None) is None


def test_detect_server_offset_refuses_a_closed_market(dying_server):
    """Every tick stale by days must not be read as an exotic timezone."""
    from phase0.collectors._client import UNIVERSE
    import subprocess, sys as _sys

    # tick_time two days behind: no plausible offset explains it.
    url = dying_server(ok_calls=10_000, tick_time="2026-09-05T09:15:00")
    proc = _run("phase0.collectors.d3a_spread_forward", url,
                "--interval", "0.1", "--once", "--symbols", "EURUSD",
                "--out", "/dev/null")
    assert proc.returncode == 0, proc.stderr
    assert '"server_utc_offset_hours": null' in proc.stdout
