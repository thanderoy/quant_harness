"""D3a — forward spread collection.

    python3 -m phase0.collectors.d3a_spread_forward --interval 60
    python3 -m phase0.collectors.d3a_spread_forward --once

Samples ``/api/v1/tick`` for every candidate symbol on a schedule and appends
bid/ask/spread with a UTC timestamp. Runs continuously from the day it is
switched on, so that when Phase 2 needs session-bucketed spread distributions
the data already exists rather than starting to accumulate then.

Per the spec this is the single highest-value MT5-dependent action available
and does not wait for the rest of D1. It only needs /api/v1/tick, which
mt5-api already exposes, so unlike D1 and D3b it is runnable the moment a
terminal is up with no API change.

Storage: JSONL, not Postgres. The spec names Postgres, and that remains right
for the durable home, but a collector that requires a database to be reachable
is a collector that stops on the first outage and loses the window it exists
to cover. Append-only JSONL keeps sampling through anything and loads into
Postgres afterwards; ``--out`` selects the file.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase0.collectors._client import (
    UNIVERSE,
    broker_context,
    EndpointMissing,
    MT5Unavailable,
    get,
    now_iso,
)

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "d3a_spread_samples.jsonl"

#: Session buckets in UTC, as named by the spec. Broker server time is
#: typically UTC+2/+3; the bucket is recorded per-sample so the boundary can be
#: re-cut later without re-collecting.
SESSIONS: tuple[tuple[str, int, int], ...] = (
    ("asia", 0, 7),
    ("london", 7, 12),
    ("overlap", 12, 16),   # London/NY overlap
    ("ny", 16, 21),
    ("offhours", 21, 24),
)

#: Rollover is sampled as its own flag rather than a bucket, because it
#: overlaps the others and its spread behaviour is the reason to look at all.
ROLLOVER_UTC_HOUR = 21
ROLLOVER_MINUTES = 15

_stop = False


def _handle_signal(signum, frame) -> None:  # noqa: ANN001
    global _stop
    _stop = True


def session_bucket(ts: datetime) -> str:
    h = ts.hour
    for name, lo, hi in SESSIONS:
        if lo <= h < hi:
            return name
    return "offhours"


def in_rollover_window(ts: datetime) -> bool:
    """Within +/- ROLLOVER_MINUTES of the daily rollover hour."""
    minutes = (ts.hour - ROLLOVER_UTC_HOUR) * 60 + ts.minute
    return abs(minutes) <= ROLLOVER_MINUTES or abs(minutes + 1440) <= ROLLOVER_MINUTES


#: Bar lengths, in seconds, that a strategy may close a bar on. A strategy
#: evaluating H1 acts at HH:00:00 plus however long it takes to wake, fetch and
#: decide; that instant is the only one whose spread it will ever pay.
TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}

#: Default delay after the boundary. A Celery beat task does not fire at
#: exactly HH:00:00 — it wakes, queues, fetches rates and only then reads a
#: price. 750ms is a deliberately conservative stand-in for that path; the
#: offset is recorded per row so a better figure can be applied later without
#: re-collecting.
DEFAULT_BAR_LATENCY_MS = 750


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def next_boundary(now: datetime, period_s: int, latency_s: float) -> datetime:
    """The next sampling instant for a bar of ``period_s`` seconds."""
    epoch = now.timestamp() - latency_s
    nxt = (int(epoch) // period_s + 1) * period_s
    return datetime.fromtimestamp(nxt + latency_s, tz=timezone.utc)


def warm_up(symbols: tuple[str, ...]) -> int:
    """Touch every symbol once and discard the result.

    mt5-api selects a symbol into MarketWatch on first request, and that first
    tick comes back degenerate — measured on Pepperstone demo, every one of the
    nine candidates returned bid == ask == spread 0.0 on first touch and real
    spreads immediately after. Recording those zeros would drag the median
    spread down with values that were never quotable, which is precisely the
    kind of quiet contamination this census exists to avoid.

    Returns the number of symbols that answered.
    """
    ok = 0
    for sym in symbols:
        try:
            get("/api/v1/tick", {"symbol": sym})
            ok += 1
        except (MT5Unavailable, EndpointMissing):
            pass
    return ok


#: A tick older than this is not a live quote. Generous enough to survive a
#: quiet minute in an illiquid symbol, short enough to catch a closed market.
STALE_TICK_SECONDS = 300


#: Offsets a broker server plausibly runs at. Pepperstone's MT5 server is
#: EET/EEST, i.e. UTC+2 or UTC+3. The range is deliberately wider than that,
#: but narrow enough that a stale weekend tick cannot masquerade as one.
PLAUSIBLE_OFFSET_HOURS = range(-12, 15)

#: How close the freshest tick must be to a whole-hour offset before that
#: offset is believed.
OFFSET_TOLERANCE_S = 120


def detect_server_utc_offset(symbols: tuple[str, ...]) -> int | None:
    """Whole-hour offset between broker server time and UTC, or None.

    mt5-api returns tick timestamps as naive broker server time. Treating
    them as UTC was wrong by the offset itself: on Pepperstone (UTC+3) it
    produced tick_age_s of -10799 on a tick that was 750ms old, which left
    `stale` unable to fire until a tick was over three hours out of date.

    Detected rather than configured, so a DST change corrects itself. The
    freshest tick across the universe is the reference: during an open market
    it is seconds old, so its lag is the offset plus a rounding error. A
    closed market makes every tick hours or days stale, which falls outside
    PLAUSIBLE_OFFSET_HOURS and returns None — an unknown offset, reported as
    an unknown age, rather than a confident wrong one.
    """
    now = datetime.now(timezone.utc)
    lags: list[float] = []
    for sym in symbols:
        try:
            payload = get("/api/v1/tick", {"symbol": sym}).payload
        except (MT5Unavailable, EndpointMissing):
            continue
        raw = payload.get("time")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        lags.append((ts - now).total_seconds())

    if not lags:
        return None
    freshest = max(lags)
    hours = round(freshest / 3600)
    if hours not in PLAUSIBLE_OFFSET_HOURS:
        return None
    if abs(freshest - hours * 3600) > OFFSET_TOLERANCE_S:
        return None
    return hours


def tick_age_seconds(tick_time: str | None, sampled_at: datetime,
                     server_utc_offset_hours: int | None = 0) -> float | None:
    """Age of the broker's tick at sampling time, in seconds.

    Returns None when the offset is unknown: an age computed against an
    unknown timezone is not a measurement.
    """
    if not tick_time or server_utc_offset_hours is None:
        return None
    try:
        ts = datetime.fromisoformat(str(tick_time))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts -= timedelta(hours=server_utc_offset_hours)
    return (sampled_at - ts).total_seconds()


def _is_stale(age: float | None) -> bool | None:
    """None when the age is unknown — not False, which asserts freshness."""
    if age is None:
        return None
    return age > STALE_TICK_SECONDS


def sample_once(symbols: tuple[str, ...], server: str | None = None,
                sample_kind: str = "periodic",
                bar_timeframe: str | None = None,
                offset_hours: int | None = 0) -> list[dict]:
    rows: list[dict] = []
    for sym in symbols:
        ts = datetime.now(timezone.utc)
        row: dict = {
            "symbol": sym,
            # Stamped per row, not once per file. An append-only file outlives
            # the process, and the collector can be restarted against a
            # different terminal; a run-level header would silently cover rows
            # it never described.
            "server": server,
            # Naive broker timestamps are server time, so every age depends on
            # this. Recorded per row: it is detected, not configured, and a
            # DST change moves it mid-file.
            "server_utc_offset_hours": offset_hours,
            # Which schedule produced this row. The periodic series is
            # time-weighted and answers "what is the spread at an arbitrary
            # moment"; the bar-boundary series is entry-conditional and
            # answers "what does a strategy acting on a closed bar actually
            # pay". They are different estimators and must not be pooled.
            "sample_kind": sample_kind,
            "bar_timeframe": bar_timeframe,
            "sampled_at_utc": ts.isoformat(),
            "session": session_bucket(ts),
            "rollover_window": in_rollover_window(ts),
        }
        try:
            payload = get("/api/v1/tick", {"symbol": sym}).payload
            bid = float(payload["bid"])
            ask = float(payload["ask"])
            spread = ask - bid
            # Computed before the update: inside a dict literal, row.get()
            # would still be reading the dict as it was before this call.
            age = tick_age_seconds(payload.get("time"), ts, offset_hours)
            row.update({
                "tick_age_s": age,
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "tick_time": payload.get("time"),
                "ok": True,
                # A zero spread is a genuine quote on a raw-spread account
                # (measured: 86% of Pepperstone EURUSD ticks, and none on
                # marked-up XAUUSD), so it is recorded as an ordinary
                # observation. A CROSSED quote is impossible and is what
                # actually warrants suspicion.
                "zero_spread": spread == 0.0,
                "crossed": spread < 0.0,
                # The endpoint returns the last known tick whether or not the
                # market is open, so a closed market yields the same Friday
                # quote every round. Over one weekend that is ~26,000 identical
                # rows at nine symbols a minute, all carrying the wide
                # at-the-close spread. Unflagged, they would dominate any
                # median computed over the file.
                "stale": _is_stale(age),
            })
        except (MT5Unavailable, EndpointMissing, KeyError, TypeError, ValueError) as exc:
            # Recorded, never dropped: a gap with no reason in it is
            # indistinguishable later from a period of zero spread.
            row.update({"ok": False, "error": str(exc)})
        rows.append(row)
    return rows


def append(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=float, default=60.0,
                    help="seconds between sampling rounds (default 60)")
    ap.add_argument("--once", action="store_true",
                    help="take a single round and exit")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symbols", nargs="*", default=list(UNIVERSE))
    ap.add_argument("--bar-timeframes", nargs="*", default=["H1", "M15"],
                    choices=sorted(TIMEFRAME_SECONDS),
                    help="also sample just after each of these bar closes "
                         "(default H1 M15; pass with no values to disable)")
    ap.add_argument("--bar-latency-ms", type=int,
                    default=DEFAULT_BAR_LATENCY_MS,
                    help="delay after the bar boundary, standing in for the "
                         f"wake/fetch/decide path (default "
                         f"{DEFAULT_BAR_LATENCY_MS})")
    ap.add_argument("--expect-server", default=None,
                    help="refuse to run unless the terminal's trade server "
                         "contains this substring (case-insensitive). Use it "
                         "whenever the output feeds a broker-specific "
                         "conclusion.")
    ap.add_argument("--max-consecutive-failures", type=int, default=30,
                    help="exit non-zero after this many rounds in which every "
                         "symbol failed (default 30; at the default interval "
                         "that is 30 minutes of a dead endpoint)")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    symbols = tuple(args.symbols)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    broker = broker_context()
    server = broker.get("server")

    if args.expect_server:
        if not server or args.expect_server.lower() not in server.lower():
            print(json.dumps({
                "aborted": True,
                "reason": "trade server does not match --expect-server",
                "expected_substring": args.expect_server,
                "actual_server": server,
            }), file=sys.stderr)
            return 3

    warmed = warm_up(symbols)
    offset_hours = detect_server_utc_offset(symbols)
    print(json.dumps({"warm_up_symbols_ok": warmed,
                      "broker": broker,
                      "server_utc_offset_hours": offset_hours,
                      "note": "first touch discarded — see warm_up()"}))

    latency_s = args.bar_latency_ms / 1000.0
    pending: dict[str, datetime] = {
        tf: next_boundary(now_utc(), TIMEFRAME_SECONDS[tf], latency_s)
        for tf in args.bar_timeframes
    }
    if pending:
        print(json.dumps({
            "bar_boundary_schedule": {tf: w.isoformat()
                                      for tf, w in pending.items()},
            "bar_latency_ms": args.bar_latency_ms,
        }))

    rounds = 0
    bar_rounds = 0
    ok_rows = 0
    zero = 0
    crossed = 0
    consecutive_dead_rounds = 0
    stale = 0
    aborted = False
    while not _stop:
        rows = sample_once(symbols, server, "periodic", None, offset_hours)
        append(args.out, rows)
        rounds += 1
        round_ok = sum(1 for r in rows if r.get("ok"))
        ok_rows += round_ok
        zero += sum(1 for r in rows if r.get("zero_spread"))
        crossed += sum(1 for r in rows if r.get("crossed"))
        stale += sum(1 for r in rows if r.get("stale"))

        # Rows are still recorded with their reason (see sample_once), but a
        # collector whose source has gone away must stop and say so. Left
        # unbounded this wrote 65,228 error rows over five days against a dead
        # mt5-test while looking, by line count and process liveness, healthy.
        if round_ok == 0:
            consecutive_dead_rounds += 1
            if consecutive_dead_rounds >= args.max_consecutive_failures:
                print(json.dumps({
                    "aborted": True,
                    "reason": "no symbol answered in "
                              f"{consecutive_dead_rounds} consecutive rounds",
                    "last_error": next((r.get("error") for r in rows
                                        if r.get("error")), None),
                }), file=sys.stderr)
                aborted = True
                break
        else:
            consecutive_dead_rounds = 0

        if args.once:
            break

        # Sleep until whichever comes first: the next periodic sample or the
        # next bar boundary. Sleeping a fixed interval and checking afterwards
        # would put the boundary sample late by up to a full interval, which
        # for the one instant the estimator exists to measure is the whole
        # error.
        next_periodic = now_utc() + timedelta(seconds=args.interval)
        while not _stop:
            # Service every boundary that is already due BEFORE deciding how
            # long to sleep. The earlier shape chose the nearest target, and
            # broke out of the wait loop when that target was already past --
            # without firing it. Nothing then advanced pending[tf], so the
            # stale boundary was re-selected on every pass, the loop never
            # slept, and the periodic schedule ran at request rate. In
            # production that ended the entry-conditional series at
            # 2026-09-12T12:30Z and wrote 19.6M periodic rows in its place.
            fired = [tf for tf, when in pending.items() if when <= now_utc()]
            for tf in fired:
                brows = sample_once(symbols, server, "bar_boundary", tf, offset_hours)
                append(args.out, brows)
                rounds += 1
                ok_rows += sum(1 for r in brows if r.get("ok"))
                zero += sum(1 for r in brows if r.get("zero_spread"))
                crossed += sum(1 for r in brows if r.get("crossed"))
                stale += sum(1 for r in brows if r.get("stale"))
                bar_rounds += 1
                # Recomputed from the clock, not from the boundary that just
                # fired, so a stall skips ahead rather than replaying a burst.
                pending[tf] = next_boundary(
                    now_utc(), TIMEFRAME_SECONDS[tf], latency_s)

            now = now_utc()
            if now >= next_periodic:
                break
            target = min([next_periodic, *pending.values()])
            wait = (target - now).total_seconds()
            if wait > 0:
                time.sleep(min(1.0, wait))

    print(json.dumps({
        "rounds": rounds,
        "bar_boundary_rounds": bar_rounds,
        "rows_written": rounds * len(symbols),
        "bar_timeframes": list(args.bar_timeframes),
        "rows_ok": ok_rows,
        "rows_zero_spread": zero,
        "rows_crossed": crossed,
        "rows_stale": stale,
        "server": server,
        "server_utc_offset_hours": offset_hours,
        "consecutive_dead_rounds_at_exit": consecutive_dead_rounds,
        "aborted_source_unreachable": aborted,
        "out": str(args.out),
        "stopped_at_utc": now_iso(),
    }, indent=2))
    if aborted:
        return 2
    return 0 if ok_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
