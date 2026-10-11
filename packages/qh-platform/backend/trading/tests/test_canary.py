"""The operational canary: what it checks, and that it cannot trade.

The never-signals/never-orders property is held three ways, so that no single
refactor can quietly remove it:

  * statically -- the canary module's AST names none of the order, close,
    modify, trade-record or state-writing entry points, and imports neither
    the broker port nor the trade-record writer;
  * structurally -- the only MT5 handle it holds exposes exactly six read
    methods and has no attribute passthrough;
  * dynamically -- an end-to-end run against a fake HTTP layer that refuses
    every endpoint outside the read allowlist, with every write entry point
    patched to raise.

No test touches a database or a real terminal.
"""

import ast
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import numpy as np
import pytest
import requests

from app.quant import canary

CANARY_SOURCE = Path(canary.__file__)

#: Names the canary module must never mention. Anything that sends, closes or
#: modifies an order, records a trade, evaluates an entry rule, or writes the
#: strategies' state files.
FORBIDDEN_NAMES = {
    "send_order", "close_position", "modify_order", "modify_position",
    "submit", "MT5Broker", "OrderRequest", "side_from_action",
    "create_trade", "create_trade_record",
    "evaluate", "_generate_signal", "_place_order", "manage_positions",
    "_check_h1_confirmation",
    "JsonPeakStore", "DrawdownGuard", "_PartialCloseTracker",
    "open", "write", "write_text", "write_bytes", "makedirs", "mkdir",
    "unlink", "rename", "touch", "rmtree",
}
FORBIDDEN_MODULES = {
    "os", "shutil", "app.adapters.broker", "app.adapters.utils.create",
    "resources.execution", "resources.execution.broker",
}

#: The only (method, path) pairs the canary may send to the MT5 API.
READ_ALLOWLIST = {
    ("GET", "/"),
    ("POST", "/api/v1/connect"),
    ("GET", "/api/v1/account"),
    ("GET", "/api/v1/rates"),
    ("GET", "/api/v1/positions"),
}

SERVER_SENTINEL = "Canary-Demo-Server"
LOGIN_SENTINEL = "LOGIN-SENTINEL-DO-NOT-LOG"
HOLDER_SENTINEL = "HOLDER-SENTINEL-DO-NOT-LOG"

# Wednesday 2026-10-07 14:03 UTC: market open, EEST (server = UTC+3).
OPEN_NOW = datetime(2026, 10, 7, 14, 3, tzinfo=timezone.utc)


# ── fake MT5 API ──────────────────────────────────────────────────────────


def json_response(payload: object, status: int = 200) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(payload).encode()
    resp.headers["content-type"] = "application/json"
    return resp


def server_stamp(t_utc: datetime) -> str:
    """How mt5-api serialises a bar time: server clock, naive ISO."""
    local = t_utc.astimezone(canary.SERVER_TZ).replace(tzinfo=None)
    return local.isoformat()


def fake_rates(now: datetime, timeframe: str, count: int,
               lag: timedelta = timedelta(0), utc_stamps: bool = False) -> list[dict]:
    """``count`` bars whose last is the bar forming at ``now - lag``."""
    minutes = canary.TIMEFRAME_MINUTES[timeframe]
    end = now - lag
    forming = end.replace(second=0, microsecond=0) - timedelta(
        minutes=(end.minute % minutes) if minutes < 60 else end.minute)
    rng = np.random.default_rng(7)
    close = 2400 + np.cumsum(rng.normal(0, 1.5, count))
    bars = []
    for i in range(count):
        t = forming - timedelta(minutes=minutes * (count - 1 - i))
        c = float(close[i])
        stamp = t.replace(tzinfo=None).isoformat() if utc_stamps else server_stamp(t)
        bars.append({"time": stamp, "open": c - 0.3, "high": c + 1.1,
                     "low": c - 1.2, "close": c, "tick_volume": 100,
                     "spread": 12, "real_volume": 0})
    return bars


class FakeMT5Api:
    """Routes requests.Session.get/post. Refuses anything not on the allowlist."""

    def __init__(self, now: datetime, positions: dict | None = None,
                 rates_lag: timedelta = timedelta(0), utc_stamps: bool = False):
        self.now = now
        self.utc_stamps = utc_stamps
        self.positions = positions or {}
        self.rates_lag = rates_lag
        self.calls: list[tuple[str, str]] = []
        self.refused: list[tuple[str, str]] = []

    def get(self, url: str, params: dict | None = None, **_kw) -> requests.Response:
        return self.route("GET", url, params or {})

    def post(self, url: str, json: dict | None = None, **_kw) -> requests.Response:
        return self.route("POST", url, json or {})

    def route(self, method: str, url: str, params: dict) -> requests.Response:
        path = urlparse(url).path
        self.calls.append((method, path))
        if (method, path) not in READ_ALLOWLIST:
            self.refused.append((method, path))
            raise AssertionError(f"canary sent {method} {path}")
        if path == "/":
            return json_response({"success": "true", "description": {
                "status": "running", "mt5_connected": "True"}})
        if path == "/api/v1/connect":
            return json_response({"success": True, "message": "connected"})
        if path == "/api/v1/account":
            return json_response({"login": LOGIN_SENTINEL, "name": HOLDER_SENTINEL,
                                  "server": SERVER_SENTINEL, "equity": 3643.21,
                                  "balance": 3650.0})
        if path == "/api/v1/rates":
            tf = params["timeframe"]
            return json_response({"symbol": params["symbol"], "timeframe": tf,
                                  "rates": fake_rates(self.now, tf, params["count"],
                                                      self.rates_lag,
                                                      self.utc_stamps)})
        return json_response(self.positions.get(int(params["magic"]), []))


def write_state(directory: Path, peak: bool = True,
                partial: bool = True) -> list[tuple[str, str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    specs = [("state_cnk_peak", str(directory / "peak_hma_stoch_1h.json"), canary.PEAK),
             ("state_asqs_peak", str(directory / "asqs_peak.json"), canary.PEAK),
             ("state_asqs_partial", str(directory / "asqs_partial.json"), canary.PARTIAL)]
    if peak:
        Path(specs[0][1]).write_text(json.dumps({"peak_equity": 3700.0}))
        Path(specs[1][1]).write_text(json.dumps({"peak_equity": 3690.5}))
    if partial:
        Path(specs[2][1]).write_text(json.dumps({"closed_tickets": [11, 12]}))
    return specs


def run_with_fake(fake: FakeMT5Api, specs: list, now: datetime | None = None,
                  environment: str = "test") -> list:
    with patch.object(requests.Session, "get", side_effect=fake.get), \
         patch.object(requests.Session, "post", side_effect=fake.post), \
         patch.object(canary, "STATE_FILES", tuple(specs)):
        return canary.run_checks(environment, now=now or fake.now)


def by_name(results: list) -> dict:
    return {r.name: r for r in results}


# ── never signals, never orders ──────────────────────────────────────────


def module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def imported_modules(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
            mods |= {f"{node.module}.{a.name}" for a in node.names}
    return mods


def test_canary_module_names_no_order_or_state_write_path():
    tree = ast.parse(CANARY_SOURCE.read_text())
    leaked = module_names(tree) & FORBIDDEN_NAMES
    assert not leaked, f"canary references forbidden names: {sorted(leaked)}"


def test_canary_module_imports_no_broker_trade_writer_or_os():
    tree = ast.parse(CANARY_SOURCE.read_text())
    leaked = {m for m in imported_modules(tree)
              if m in FORBIDDEN_MODULES
              or any(m.startswith(f"{f}.") for f in FORBIDDEN_MODULES)}
    assert not leaked, f"canary imports forbidden modules: {sorted(leaked)}"


def test_the_ast_scan_would_catch_a_regression():
    """Guard the guard: the scan must flag the obvious ways back in."""
    for snippet in ("client.send_order(x)", "from app.adapters.broker import MT5Broker",
                    "self._client.close_position(1)", "Path(p).write_text('x')",
                    "open(p, 'w')", "JsonPeakStore(p)"):
        assert module_names(ast.parse(snippet)) & FORBIDDEN_NAMES, snippet
    assert imported_modules(ast.parse("import os")) & FORBIDDEN_MODULES


def test_read_only_handle_exposes_exactly_the_read_methods():
    public = {n for n in vars(canary.ReadOnlyMT5) if not n.startswith("_")}
    assert public == {"health", "connect", "account", "rates", "positions", "release"}
    assert "__getattr__" not in vars(canary.ReadOnlyMT5)
    handle = canary.ReadOnlyMT5("http://mt5-test:5001")
    for name in ("send_order", "close_position", "modify_order", "modify_position",
                 "submit", "get_deals"):
        assert not hasattr(handle, name), name
    handle.release()


def test_end_to_end_run_touches_only_read_endpoints(tmp_path):
    """Every write entry point raises; the task still completes, all OK."""
    from app.adapters import broker, mt5_api
    from app.adapters.utils import create
    from app.quant.strategies.asqs import strategy as asqs_strategy
    from app.quant.strategies.crest_n_keel import strategy as cnk_strategy

    trap = MagicMock(side_effect=AssertionError("write path reached"))
    fake = FakeMT5Api(datetime.now(timezone.utc))
    specs = write_state(tmp_path / "state")
    with patch.object(mt5_api.MT5APIClient, "send_order", trap), \
         patch.object(mt5_api.MT5APIClient, "close_position", trap), \
         patch.object(mt5_api.MT5APIClient, "modify_order", trap), \
         patch.object(mt5_api.MT5APIClient, "modify_position", trap), \
         patch.object(broker.MT5Broker, "submit", trap), \
         patch.object(create, "create_trade", trap), \
         patch.object(cnk_strategy, "create_trade_record", trap), \
         patch.object(asqs_strategy, "create_trade_record", trap), \
         patch.object(requests.Session, "get", side_effect=fake.get), \
         patch.object(requests.Session, "post", side_effect=fake.post), \
         patch.object(canary, "STATE_FILES", tuple(specs)):
        result = canary.run_canary.run(environment="test")

    trap.assert_not_called()
    assert fake.refused == []
    assert set(fake.calls) <= READ_ALLOWLIST
    assert ("POST", "/api/v1/connect") in fake.calls
    assert result["env"] == "test"
    assert "error" not in result
    statuses = {k: v["status"] for k, v in result["checks"].items()}
    assert set(statuses.values()) <= {canary.OK, canary.WARN}, statuses


def test_state_files_are_never_written_or_created(tmp_path):
    state = tmp_path / "state"
    specs = write_state(state)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()}
    absent_dir = tmp_path / "never-created"
    specs.append(("state_extra", str(absent_dir / "peak.json"), canary.PEAK))

    run_with_fake(FakeMT5Api(OPEN_NOW), specs)

    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in state.iterdir()}
    assert after == before
    assert not absent_dir.exists()


def test_task_is_registered_under_its_beat_name():
    from app.config.celery import app as celery_app
    import app.quant.tasks  # noqa: F401  (registration happens on import)

    assert "quant.canary.run" in celery_app.tasks


# ── the checks ────────────────────────────────────────────────────────────


def test_healthy_open_market_is_all_ok(tmp_path):
    results = by_name(run_with_fake(FakeMT5Api(OPEN_NOW), write_state(tmp_path)))
    assert {n: r.status for n, r in results.items() if r.status != canary.OK} == {}
    assert canary.overall_status(list(results.values())) == canary.OK
    assert results["bars_H1"].detail["market_open"] is True
    assert results["bars_M5"].detail["open_market_age_min"] < 5
    for key in ("hma", "stoch_k", "stoch_d", "atr"):
        assert math.isfinite(results["indicators_H1"].detail[key])
    assert results["state_asqs_partial"].detail["closed_tickets"] == 2


def test_account_reports_server_and_equity_only(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    fake = FakeMT5Api(OPEN_NOW)
    with patch.object(requests.Session, "get", side_effect=fake.get), \
         patch.object(requests.Session, "post", side_effect=fake.post), \
         patch.object(canary, "STATE_FILES", tuple(write_state(tmp_path))):
        result = canary.run_canary.run(environment="test")
    assert result["checks"]["account"] == {"status": canary.OK,
                                           "server": SERVER_SENTINEL, "equity": 3643.21}
    blob = json.dumps(result) + caplog.text
    assert LOGIN_SENTINEL not in blob
    assert HOLDER_SENTINEL not in blob


def test_one_structured_summary_line_per_run(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    fake = FakeMT5Api(OPEN_NOW)
    with patch.object(requests.Session, "get", side_effect=fake.get), \
         patch.object(requests.Session, "post", side_effect=fake.post), \
         patch.object(canary, "STATE_FILES", tuple(write_state(tmp_path))):
        canary.run_canary.run(environment="test")
    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("[CANARY] summary ")]
    assert len(lines) == 1
    summary = json.loads(lines[0].removeprefix("[CANARY] summary "))
    assert summary["env"] == "test"
    assert set(summary["checks"]) >= {"api_health", "connect", "account", "bars_H1",
                                      "bars_M5", "indicators_H1", "indicators_M5",
                                      "positions_crest_n_keel", "positions_asqs",
                                      "state_cnk_peak", "state_asqs_peak",
                                      "state_asqs_partial"}


def test_unreachable_api_fails_without_raising_and_still_reads_state(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    down = MagicMock(side_effect=requests.ConnectionError("refused"))
    with patch.object(requests.Session, "get", down), \
         patch.object(requests.Session, "post", down), \
         patch.object(canary, "STATE_FILES", tuple(write_state(tmp_path))):
        result = canary.run_canary.run(environment="test")
    checks = result["checks"]
    assert result["status"] == canary.FAIL
    assert checks["api_health"]["status"] == canary.FAIL
    assert checks["bars_H1"]["status"] == canary.SKIP
    assert checks["state_cnk_peak"]["status"] == canary.OK
    assert down.call_count == 1  # no timeout cascade after health fails
    assert any(r.levelno == logging.ERROR and "api_health FAIL" in r.getMessage()
               for r in caplog.records)


def test_unknown_environment_is_a_failed_run_not_a_crash():
    result = canary.run_canary.run(environment="staging")
    assert result["status"] == canary.FAIL
    assert "Unknown MT5 environment" in result["error"]


def test_prod_environment_targets_the_live_url(tmp_path):
    fake = FakeMT5Api(OPEN_NOW)
    with patch.object(canary, "ReadOnlyMT5", wraps=canary.ReadOnlyMT5) as handle:
        run_with_fake(fake, write_state(tmp_path), environment="prod")
    assert handle.call_args.args[0] == canary.settings.MT5_API_URL


def test_stale_feed_during_open_market_fails(tmp_path):
    fake = FakeMT5Api(OPEN_NOW, rates_lag=timedelta(hours=5))
    results = by_name(run_with_fake(fake, write_state(tmp_path)))
    assert results["bars_H1"].status == canary.FAIL
    assert results["bars_M5"].status == canary.FAIL


@pytest.mark.parametrize("positions,schedule_has_asqs,env,expected", [
    ([], False, "test", canary.OK),
    ([{"ticket": 1}], True, "test", canary.OK),        # asqs still manages it
    ([{"ticket": 1}], False, "test", canary.WARN),     # asqs off the schedule
    ([{"ticket": 1}], True, "prod", canary.WARN),      # asqs trades test, not prod
])
def test_positions_by_magic(tmp_path, positions, schedule_has_asqs, env, expected):
    asqs = next(w for w in canary.WATCHED_STRATEGIES if w.name == "asqs")
    schedule = {"asqs": {"task": asqs.task_name}} if schedule_has_asqs else {}
    fake = FakeMT5Api(OPEN_NOW, positions={asqs.magic: positions})
    with patch.object(canary.settings, "CELERY_BEAT_SCHEDULE", schedule):
        results = by_name(run_with_fake(fake, write_state(tmp_path), environment=env))
    assert results["positions_asqs"].status == expected
    assert results["positions_asqs"].detail["open"] == len(positions)
    assert results["positions_crest_n_keel"].status == canary.OK


def test_watched_strategies_match_the_strategies_own_defaults():
    from app.quant.strategies.asqs import strategy as asqs_strategy
    from app.quant.strategies.crest_n_keel import strategy as cnk_strategy

    magics = {w.name: w.magic for w in canary.WATCHED_STRATEGIES}
    assert magics == {"crest_n_keel": cnk_strategy.MAGIC_NUMBER,
                      "asqs": asqs_strategy.MAGIC_NUMBER}
    paths = {spec[1] for spec in canary.STATE_FILES}
    assert paths == {cnk_strategy.DEFAULT_PEAK_STORE_PATH,
                     asqs_strategy.DEFAULT_PEAK_STORE_PATH,
                     asqs_strategy.DEFAULT_PARTIAL_STORE_PATH}
    assert all(w.environment == "test" for w in canary.WATCHED_STRATEGIES)


@pytest.mark.parametrize("peak,partial,expected", [
    (False, True, {"state_cnk_peak": canary.WARN, "state_asqs_peak": canary.WARN,
                   "state_asqs_partial": canary.OK}),
    (True, False, {"state_cnk_peak": canary.OK, "state_asqs_peak": canary.OK,
                   "state_asqs_partial": canary.OK}),
])
def test_missing_state_files(tmp_path, peak, partial, expected):
    specs = write_state(tmp_path, peak=peak, partial=partial)
    results = [canary.check_state_file(*s) for s in specs]
    assert {r.name: r.status for r in results} == expected
    present = {r.name: r.detail["present"] for r in results}
    assert present == {"state_cnk_peak": peak, "state_asqs_peak": peak,
                       "state_asqs_partial": partial}


@pytest.mark.parametrize("content,kind", [
    ("{not json", canary.PEAK),
    ('{"peak": 1}', canary.PEAK),
    ('{"peak_equity": "abc"}', canary.PEAK),
    ('{"peak_equity": 0}', canary.PEAK),
    ('{"closed_tickets": 5}', canary.PARTIAL),
    ("[]", canary.PARTIAL),
])
def test_malformed_state_file_fails(tmp_path, content, kind):
    path = tmp_path / "state.json"
    path.write_text(content)
    assert canary.check_state_file("s", str(path), kind).status == canary.FAIL


def test_unreadable_state_path_fails(tmp_path):
    """A directory where the file should be: present but not readable."""
    (tmp_path / "peak.json").mkdir()
    assert canary.check_state_file("s", str(tmp_path / "peak.json"),
                                   canary.PEAK).status == canary.FAIL


# ── bar freshness and the market calendar ────────────────────────────────


def ny(*args: int) -> datetime:
    return datetime(*args, tzinfo=canary.MARKET_TZ).astimezone(timezone.utc)


@pytest.mark.parametrize("label,now,expected", [
    ("Wed 10:00 NY", ny(2026, 10, 7, 10, 0), True),
    ("Wed 17:30 NY daily break", ny(2026, 10, 7, 17, 30), False),
    ("Wed 18:00 NY reopen", ny(2026, 10, 7, 18, 0), True),
    ("Fri 16:59 NY", ny(2026, 10, 9, 16, 59), True),
    ("Fri 17:00 NY weekly close", ny(2026, 10, 9, 17, 0), False),
    ("Sat", ny(2026, 10, 10, 12, 0), False),
    ("Sun 17:59 NY", ny(2026, 10, 11, 17, 59), False),
    ("Sun 18:00 NY weekly open", ny(2026, 10, 11, 18, 0), True),
    ("winter Fri 16:30 NY", ny(2026, 12, 4, 16, 30), True),
    ("winter Sat", ny(2026, 12, 5, 9, 0), False),
])
def test_market_calendar(label, now, expected):
    assert canary.market_is_open(now) is expected, label


@pytest.mark.parametrize("label,bar_close,now,tf,expected", [
    # Weekend: Friday's last H1 bar closed at the weekly close; nothing new
    # since, and none expected, so Saturday and Sunday are OK.
    ("Saturday", ny(2026, 10, 9, 17, 0), ny(2026, 10, 10, 12, 0), "H1", canary.OK),
    ("Sunday pre-open", ny(2026, 10, 9, 17, 0), ny(2026, 10, 11, 17, 55), "H1", canary.OK),
    # Closed bar = iloc[-2]: on a closed market it closes one bar before the end.
    ("Saturday iloc[-2]", ny(2026, 10, 9, 16, 0), ny(2026, 10, 10, 12, 0), "H1", canary.OK),
    ("Saturday M5", ny(2026, 10, 9, 16, 55), ny(2026, 10, 10, 12, 0), "M5", canary.OK),
    # After the reopen, only open-market minutes count: 90 of them.
    ("Sunday 19:30 no new bars", ny(2026, 10, 9, 17, 0), ny(2026, 10, 11, 19, 30), "H1", canary.WARN),
    ("Sunday 18:05 M5 first bar pending", ny(2026, 10, 9, 17, 0), ny(2026, 10, 11, 18, 5), "M5", canary.OK),
    ("Sunday 18:40 M5 nothing", ny(2026, 10, 9, 17, 0), ny(2026, 10, 11, 18, 40), "M5", canary.FAIL),
    # The daily break is not counted either.
    ("daily break", ny(2026, 10, 7, 17, 0), ny(2026, 10, 7, 17, 50), "M5", canary.OK),
    ("just after break", ny(2026, 10, 7, 17, 0), ny(2026, 10, 7, 18, 4), "M5", canary.OK),
    # Open market.
    ("fresh H1", ny(2026, 10, 7, 10, 0), ny(2026, 10, 7, 10, 3), "H1", canary.OK),
    ("H1 one bar late", ny(2026, 10, 7, 10, 0), ny(2026, 10, 7, 11, 20), "H1", canary.WARN),
    ("H1 four hours late", ny(2026, 10, 7, 9, 0), ny(2026, 10, 7, 13, 1), "H1", canary.FAIL),
    ("M5 stale 20m", ny(2026, 10, 7, 10, 0), ny(2026, 10, 7, 10, 20), "M5", canary.WARN),
    # Wrong server-time assumption shows up as a closed bar in the future.
    ("future bar", ny(2026, 10, 7, 13, 0), ny(2026, 10, 7, 10, 3), "H1", canary.FAIL),
    # A feed dead for over a week fails without walking the calendar.
    ("dead for weeks", ny(2026, 9, 1, 10, 0), ny(2026, 10, 7, 10, 0), "H1", canary.FAIL),
])
def test_bar_freshness(label, bar_close, now, tf, expected):
    assert canary.freshness_status(bar_close, now, tf).status == expected, label


def test_future_bar_names_the_clock_assumption():
    result = canary.freshness_status(ny(2026, 10, 7, 13, 0), ny(2026, 10, 7, 10, 3), "H1")
    assert "SERVER_TZ" in result.detail["error"]


@pytest.mark.parametrize("stamp,expected_utc", [
    ("2026-10-07T15:00:00", datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)),   # EEST
    ("2026-01-14T15:00:00", datetime(2026, 1, 14, 13, 0, tzinfo=timezone.utc)),   # EET
])
def test_server_time_is_eet_eest(stamp, expected_utc):
    import pandas as pd

    assert canary.server_time_to_utc(pd.Timestamp(stamp)) == expected_utc


def test_bars_stamped_in_utc_are_caught_as_stale(tmp_path):
    """If a terminal ever reports UTC rather than server time, the closed bar
    looks 3h old during EEST -- the canary flags it instead of passing."""
    fake = FakeMT5Api(OPEN_NOW, utc_stamps=True)
    results = by_name(run_with_fake(fake, write_state(tmp_path)))
    assert results["bars_M5"].status == canary.FAIL
    assert results["bars_H1"].status == canary.FAIL
