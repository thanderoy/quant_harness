"""Operational canary: the strategies' live read path, with no way to trade.

crest_n_keel and asqs ran on the demo beat schedule for one week (ruling R13)
as engineering fixtures. When that week ends they come off -- a killed
mechanism does not sit on a live schedule (X29) -- and this task keeps the
monitoring value they provided: every run exercises the same code paths a
strategy walks before it decides anything, and reports which ones broke.

Each run, read-only:

  * ``api_health``   GET / on the MT5 API -- reachable, terminal connected?
  * ``connect``      POST /api/v1/connect, exactly as each strategy does on
                     construction (terminal initialise; no credentials sent).
  * ``account``      equity and server name. Never login or holder name.
  * ``bars_H1`` / ``bars_M5``  XAUUSD rates; the last CLOSED bar (iloc[-2])
                     must be fresh, measured in open-market minutes so a
                     weekend or the daily break never alerts.
  * ``indicators_H1`` / ``indicators_M5``  the ``resources`` indicators the
                     strategies import, on the closed bar, with each
                     strategy's own default periods. Values only -- no rule.
  * ``positions_<strategy>``  open positions by magic number. A position
                     whose strategy is no longer scheduled is unmanaged.
  * ``state_<file>`` the drawdown-guard peak files and the asqs partial-close
                     tracker, read as bytes and parsed. Never opened for
                     writing, never created.

**It never signals and never orders, by construction.** The only MT5 handle
it holds is :class:`ReadOnlyMT5`, a whitelist wrapper with no attribute
passthrough, so ``send_order``, ``close_position`` and ``modify_*`` are not
reachable from here. It does not import the broker port, the trade-record
writer, the peak store or the partial-close tracker (both of the latter
create directories and write files). It evaluates no entry rule.
``tests/test_canary.py`` holds all of this: an AST scan of this module for
the forbidden names, and an end-to-end run against a fake HTTP layer that
raises on any endpoint outside the read allowlist.

Bar timestamps arrive in broker SERVER time stamped as if UTC (mt5-api does
``pd.to_datetime(..., unit="s")`` on MT5's epoch). Both terminals run the
MetaQuotes EET/EEST convention -- see ``research/post/sweeps/data.py`` -- so
they are localised to Europe/Athens here. If that assumption is ever wrong
the check says so: a closed bar in the future is a FAIL naming the clock.
"""

import inspect
import json
import math
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from celery import shared_task

from app.adapters.mt5_api import MT5APIClient
from app.config import settings
from app.quant.strategies.asqs import strategy as asqs_module
from app.quant.strategies.crest_n_keel import strategy as cnk_module
from app.quant.strategies.indicators import atr, hma, stochastic
from app.quant.strategies.logging_utils import get_strategy_logger

SHORT_NAME = "CANARY"
LOGGER = get_strategy_logger(__name__, SHORT_NAME)

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"
SEVERITY = {OK: 0, SKIP: 0, WARN: 1, FAIL: 2}

SYMBOL = cnk_module.SYMBOL
DEFAULT_ENVIRONMENT = "test"

#: Broker server clock (MetaQuotes EET/EEST convention, DST-aware).
SERVER_TZ = ZoneInfo("Europe/Athens")
#: Spot gold trades Sun 18:00 -> Fri 17:00 New York, with a daily break
#: 17:00-18:00 New York Mon-Thu (Pepperstone: 23:59-01:01 server time).
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_CLOSE_HOUR_NY = 17
MARKET_OPEN_HOUR_NY = 18

TIMEFRAME_MINUTES = {"H1": 60, "M5": 5}
#: (warn, fail) thresholds on the closed bar's age in OPEN-MARKET minutes.
#: With the market open the closed bar's close is the forming bar's open, so
#: a healthy age is always below one bar length; the margin covers the first
#: tick after a reopen and a late beat pickup.
FRESHNESS_LIMITS_MIN = {"H1": (70, 180), "M5": (10, 30)}
#: A closed bar this far ahead of now means the server-time assumption broke.
FUTURE_TOLERANCE = timedelta(minutes=2)
#: Beyond this wall-clock gap the feed is dead whatever the calendar says.
MAX_WALL_GAP = timedelta(days=8)

API_TIMEOUT_S = settings.REQUEST_TIMEOUT


def init_default(cls: type, param: str) -> Any:
    """A strategy's constructor default -- the value it actually runs with."""
    return inspect.signature(cls.__init__).parameters[param].default


CNK_CLS = cnk_module.CrestNKeelStrategy
ASQS_CLS = asqs_module.ASQSafeScalpingStrategy

#: Rates requested per timeframe: what each timeframe's strategy requests.
RATES_COUNT = {
    "H1": init_default(CNK_CLS, "candle_count"),
    "M5": init_default(ASQS_CLS, "candle_count"),
}


@dataclass(frozen=True)
class WatchedStrategy:
    """A strategy whose live footprint the canary watches."""

    name: str
    task_name: str
    magic: int
    environment: str


WATCHED_STRATEGIES = (
    WatchedStrategy("crest_n_keel", "quant.crest_n_keel.run",
                    init_default(CNK_CLS, "magic_number"),
                    init_default(CNK_CLS, "environment")),
    WatchedStrategy("asqs", "quant.asqs.run",
                    init_default(ASQS_CLS, "magic_number"),
                    init_default(ASQS_CLS, "environment")),
)

PEAK = "peak"
PARTIAL = "partial"

#: (check name, path, kind). Paths are the strategies' own defaults.
STATE_FILES = (
    ("state_cnk_peak", init_default(CNK_CLS, "peak_store_path"), PEAK),
    ("state_asqs_peak", init_default(ASQS_CLS, "peak_store_path"), PEAK),
    ("state_asqs_partial", init_default(ASQS_CLS, "partial_store_path"), PARTIAL),
)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: dict = field(default_factory=dict)


class ReadOnlyMT5:
    """The only MT5 handle the canary holds.

    A whitelist, not a filter: it wraps the client privately and forwards
    exactly these read calls. There is deliberately no ``__getattr__``, so
    ``send_order``, ``close_position`` and ``modify_*`` do not exist here.
    """

    def __init__(self, base_url: str, timeout: float = API_TIMEOUT_S):
        self._client = MT5APIClient(base_url=base_url, timeout=timeout)

    def health(self) -> dict:
        return self._client.health()

    def connect(self) -> dict:
        return self._client.connect()

    def account(self) -> dict:
        return self._client.get_account_info()

    def rates(self, symbol: str, timeframe: str, count: int) -> dict:
        return self._client.get_market_rates(symbol, timeframe, count=count)

    def positions(self, magic: int, symbol: str) -> list:
        return self._client.get_open_positions(magic=magic, symbol=symbol)

    def release(self) -> None:
        """Close the HTTP session (not a position)."""
        self._client.close()


# ── market calendar ────────────────────────────────────────────────────────


def market_is_open(t_utc: datetime) -> bool:
    """Whether spot gold is trading at ``t_utc``, by the New York clock."""
    ny = t_utc.astimezone(MARKET_TZ)
    weekday, hour = ny.weekday(), ny.hour
    if weekday == 5:
        return False
    if weekday == 6:
        return hour >= MARKET_OPEN_HOUR_NY
    if weekday == 4:
        return hour < MARKET_CLOSE_HOUR_NY
    return not (MARKET_CLOSE_HOUR_NY <= hour < MARKET_OPEN_HOUR_NY)


def open_market_minutes(start: datetime, end: datetime, cap: int) -> int:
    """Whole minutes in [start, end) during which the market was open.

    Counts up to ``cap + 1`` and stops: callers only need to know whether a
    threshold was crossed, and this keeps a stale-for-days feed cheap.
    """
    minutes = 0
    t = start
    step = timedelta(minutes=1)
    while t < end and minutes <= cap:
        if market_is_open(t):
            minutes += 1
        t += step
    return minutes


def server_time_to_utc(ts: pd.Timestamp) -> datetime:
    """A bar stamp from mt5-api (server clock, naive) as an aware UTC time."""
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").to_pydatetime()
    return ts.to_pydatetime().replace(tzinfo=SERVER_TZ).astimezone(timezone.utc)


# ── checks ────────────────────────────────────────────────────────────────


def check_api_health(mt5: ReadOnlyMT5) -> CheckResult:
    try:
        payload = mt5.health()
    except Exception as e:
        return CheckResult("api_health", FAIL, {"error": type(e).__name__})
    description = payload.get("description") if isinstance(payload, dict) else None
    connected = str((description or {}).get("mt5_connected", ""))
    if connected == "True":
        return CheckResult("api_health", OK, {"mt5_connected": True})
    return CheckResult("api_health", WARN, {"mt5_connected": False,
                                            "note": "connect follows"})


def check_connect(mt5: ReadOnlyMT5) -> CheckResult:
    try:
        mt5.connect()
    except Exception as e:
        return CheckResult("connect", FAIL, {"error": str(e)[:200]})
    return CheckResult("connect", OK)


def check_account(mt5: ReadOnlyMT5) -> CheckResult:
    """Equity and server name only -- never login or holder name."""
    try:
        info = mt5.account()
        equity = float(info.get("equity"))
        server = str(info.get("server", ""))
    except Exception as e:
        return CheckResult("account", FAIL, {"error": type(e).__name__})
    detail = {"server": server, "equity": round(equity, 2)}
    if not math.isfinite(equity) or equity <= 0:
        return CheckResult("account", FAIL, {**detail, "error": "equity not positive"})
    return CheckResult("account", OK, detail)


def rates_frame(payload: Any) -> Optional[pd.DataFrame]:
    """Rates as the strategies build them, or None if the payload is unusable."""
    if not isinstance(payload, dict) or not payload.get("rates"):
        return None
    df = pd.DataFrame(payload["rates"])
    if not {"time", "open", "high", "low", "close"} <= set(df.columns):
        return None
    if not pd.api.types.is_datetime64_any_dtype(df["time"]):
        df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time").reset_index(drop=True)


def freshness_status(bar_close_utc: datetime, now: datetime,
                     timeframe: str) -> CheckResult:
    """Grade the closed bar's age; the weekend and daily break do not count."""
    name = f"bars_{timeframe}"
    warn_min, fail_min = FRESHNESS_LIMITS_MIN[timeframe]
    detail: dict = {"closed_bar_close_utc": bar_close_utc.isoformat(timespec="minutes"),
                    "market_open": market_is_open(now)}
    if bar_close_utc > now + FUTURE_TOLERANCE:
        detail["error"] = ("closed bar is in the future: server-time "
                           "assumption (SERVER_TZ) is wrong for this terminal")
        return CheckResult(name, FAIL, detail)
    if now - bar_close_utc > MAX_WALL_GAP:
        detail["error"] = "no closed bar in over a week"
        return CheckResult(name, FAIL, detail)
    age = open_market_minutes(bar_close_utc, now, cap=fail_min)
    detail["open_market_age_min"] = age
    if age > fail_min:
        return CheckResult(name, FAIL, detail)
    if age > warn_min:
        return CheckResult(name, WARN, detail)
    return CheckResult(name, OK, detail)


def check_bars(mt5: ReadOnlyMT5, timeframe: str,
               now: datetime) -> tuple[CheckResult, Optional[pd.DataFrame]]:
    name = f"bars_{timeframe}"
    try:
        df = rates_frame(mt5.rates(SYMBOL, timeframe, RATES_COUNT[timeframe]))
    except Exception as e:
        return CheckResult(name, FAIL, {"error": str(e)[:200]}), None
    if df is None or len(df) < 3:
        return CheckResult(name, FAIL, {"error": "no usable rates"}), None
    bar_open = server_time_to_utc(pd.Timestamp(df.iloc[-2]["time"]))
    bar_close = bar_open + timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    result = freshness_status(bar_close, now, timeframe)
    result.detail["bars"] = len(df)
    return result, df


def closed_values(name: str, values: dict) -> CheckResult:
    """OK when every indicator is finite on the closed bar."""
    bad = [k for k, v in values.items() if v is None or not math.isfinite(v)]
    detail = {k: (round(v, 4) if v is not None and math.isfinite(v) else None)
              for k, v in values.items()}
    if bad:
        detail["error"] = f"non-finite on closed bar: {bad}"
        return CheckResult(name, FAIL, detail)
    return CheckResult(name, OK, detail)


def check_indicators_h1(df: Optional[pd.DataFrame]) -> CheckResult:
    """crest_n_keel's indicator path (HMA, stochastic, ATR) on iloc[-2]."""
    name = "indicators_H1"
    if df is None:
        return CheckResult(name, SKIP, {"reason": "no H1 bars"})
    try:
        hma_series = hma(df["close"], init_default(CNK_CLS, "hma_period"))
        k, d = stochastic(df["high"], df["low"], df["close"],
                          init_default(CNK_CLS, "stoch_k_period"),
                          init_default(CNK_CLS, "stoch_d_period"),
                          init_default(CNK_CLS, "stoch_smooth_k"))
        atr_series = atr(df["high"], df["low"], df["close"],
                         init_default(CNK_CLS, "atr_period"))
        values = {"hma": float(hma_series.iloc[-2]), "stoch_k": float(k.iloc[-2]),
                  "stoch_d": float(d.iloc[-2]), "atr": float(atr_series.iloc[-2])}
    except Exception as e:
        return CheckResult(name, FAIL, {"error": f"{type(e).__name__}: {e}"[:200]})
    return closed_values(name, values)


def check_indicators_m5(df: Optional[pd.DataFrame]) -> CheckResult:
    """asqs's shared-indicator path (ATR) on iloc[-2]."""
    name = "indicators_M5"
    if df is None:
        return CheckResult(name, SKIP, {"reason": "no M5 bars"})
    try:
        atr_series = atr(df["high"], df["low"], df["close"],
                         init_default(ASQS_CLS, "atr_period"))
        values = {"atr": float(atr_series.iloc[-2])}
    except Exception as e:
        return CheckResult(name, FAIL, {"error": f"{type(e).__name__}: {e}"[:200]})
    return closed_values(name, values)


def scheduled_task_names() -> set[str]:
    return {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}


def check_positions(mt5: ReadOnlyMT5, watched: WatchedStrategy,
                    environment: str) -> CheckResult:
    """Open positions under a strategy's magic number.

    Any such position is managed only if the strategy is still on the beat
    schedule AND trades the terminal being watched. Otherwise nothing will
    move its stop or close it, which is a finding.
    """
    name = f"positions_{watched.name}"
    try:
        positions = mt5.positions(watched.magic, SYMBOL) or []
    except Exception as e:
        return CheckResult(name, FAIL, {"error": str(e)[:200]})
    managed = (watched.task_name in scheduled_task_names()
               and watched.environment == environment)
    detail = {"magic": watched.magic, "open": len(positions), "managed": managed}
    if positions and not managed:
        detail["error"] = "open position with no scheduled strategy managing it"
        return CheckResult(name, WARN, detail)
    return CheckResult(name, OK, detail)


def parse_state(raw: bytes, kind: str) -> dict:
    """Validate a state file's content; raises on anything a strategy would reject."""
    data = json.loads(raw)
    if kind == PEAK:
        peak = float(data["peak_equity"])
        if not math.isfinite(peak) or peak <= 0:
            raise ValueError("peak_equity not positive")
        return {"peak_equity": round(peak, 2)}
    tickets = data["closed_tickets"]
    if not isinstance(tickets, list):
        raise TypeError("closed_tickets is not a list")
    return {"closed_tickets": len(tickets)}


def check_state_file(name: str, path: str, kind: str) -> CheckResult:
    """Read one state file without writing, creating or locking anything.

    A missing peak file makes the guard take current equity as a fresh peak
    with its whole budget unspent (JsonPeakStore's R12 hazard) -- WARN. A
    missing partial-close tracker is normal until the first TP1 partial close
    -- OK, reported as absent. Unreadable or malformed is FAIL for either.
    """
    detail: dict = {"path": path}
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        detail["present"] = False
        if kind == PARTIAL:
            detail["note"] = "absent; normal until the first TP1 partial close"
            return CheckResult(name, OK, detail)
        detail["error"] = "missing: the guard would restart from current equity"
        return CheckResult(name, WARN, detail)
    except OSError as e:
        detail["error"] = f"unreadable ({type(e).__name__})"
        return CheckResult(name, FAIL, detail)
    detail["present"] = True
    try:
        detail.update(parse_state(raw, kind))
    except (ValueError, KeyError, TypeError) as e:
        detail["error"] = f"malformed ({type(e).__name__})"
        return CheckResult(name, FAIL, detail)
    return CheckResult(name, OK, detail)


# ── run ────────────────────────────────────────────────────────────────────


def run_api_checks(mt5: ReadOnlyMT5, environment: str,
                   now: datetime) -> list[CheckResult]:
    health = check_api_health(mt5)
    if health.status == FAIL:
        skipped = ["connect", "account", "bars_H1", "bars_M5", "indicators_H1",
                   "indicators_M5"] + [f"positions_{w.name}" for w in WATCHED_STRATEGIES]
        return [health] + [CheckResult(n, SKIP, {"reason": "API unreachable"})
                           for n in skipped]
    results = [health, check_connect(mt5), check_account(mt5)]
    h1, h1_df = check_bars(mt5, "H1", now)
    m5, m5_df = check_bars(mt5, "M5", now)
    results += [h1, m5, check_indicators_h1(h1_df), check_indicators_m5(m5_df)]
    results += [check_positions(mt5, w, environment) for w in WATCHED_STRATEGIES]
    return results


def run_checks(environment: str = DEFAULT_ENVIRONMENT,
               now: Optional[datetime] = None) -> list[CheckResult]:
    """Every check, in order. Never raises for a failing dependency."""
    now = now or datetime.now(timezone.utc)
    mt5 = ReadOnlyMT5(settings.get_mt5_url(environment))
    try:
        results = run_api_checks(mt5, environment, now)
    finally:
        mt5.release()
    results += [check_state_file(*spec) for spec in STATE_FILES]
    return results


def overall_status(results: list[CheckResult]) -> str:
    worst = max((SEVERITY[r.status] for r in results), default=0)
    return {0: OK, 1: WARN, 2: FAIL}[worst]


def log_results(environment: str, results: list[CheckResult], overall: str,
                duration: float) -> None:
    """One WARNING/ERROR line per finding, then one structured summary line."""
    for r in results:
        if r.status == WARN:
            LOGGER.warning("%s WARN env=%s %s", r.name, environment,
                           json.dumps(r.detail, default=str))
        elif r.status == FAIL:
            LOGGER.error("%s FAIL env=%s %s", r.name, environment,
                         json.dumps(r.detail, default=str))
    summary = {"env": environment, "overall": overall,
               "checks": {r.name: r.status for r in results},
               "duration_s": duration}
    level = {OK: 20, WARN: 30, FAIL: 40}[overall]
    LOGGER.log(level, "summary %s", json.dumps(summary))


@shared_task(name="quant.canary.run", max_retries=0, time_limit=180,
             soft_time_limit=150)
def run_canary(environment: str = DEFAULT_ENVIRONMENT) -> dict:
    """Beat entry point. Read-only; logs and returns, never raises."""
    start = _time.monotonic()
    fired_at = datetime.now(timezone.utc)
    try:
        results = run_checks(environment, now=fired_at)
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception("run failed env=%s after %ss: %s", environment, duration, e)
        return {"status": FAIL, "env": environment, "error": str(e),
                "fired_at": fired_at.isoformat(), "duration_s": duration}
    duration = round(_time.monotonic() - start, 2)
    overall = overall_status(results)
    log_results(environment, results, overall, duration)
    return {"status": overall, "env": environment,
            "fired_at": fired_at.isoformat(), "duration_s": duration,
            "checks": {r.name: {"status": r.status, **r.detail} for r in results}}
