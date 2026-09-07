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
from datetime import datetime, timezone
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


def tick_age_seconds(tick_time: str | None, sampled_at: datetime) -> float | None:
    """Age of the broker's tick at sampling time, in seconds."""
    if not tick_time:
        return None
    try:
        ts = datetime.fromisoformat(tick_time)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        # mt5-api returns broker server time without an offset. Treated as UTC
        # for age purposes only; the raw value is kept in `tick_time` so a
        # later correction does not need re-collection.
        ts = ts.replace(tzinfo=timezone.utc)
    return (sampled_at - ts).total_seconds()


def _is_stale(age: float | None) -> bool:
    return age is not None and age > STALE_TICK_SECONDS


def sample_once(symbols: tuple[str, ...], server: str | None = None) -> list[dict]:
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
            age = tick_age_seconds(payload.get("time"), ts)
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
    print(json.dumps({"warm_up_symbols_ok": warmed,
                      "broker": broker,
                      "note": "first touch discarded — see warm_up()"}))

    rounds = 0
    ok_rows = 0
    zero = 0
    crossed = 0
    consecutive_dead_rounds = 0
    stale = 0
    aborted = False
    while not _stop:
        rows = sample_once(symbols, server)
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
        slept = 0.0
        while slept < args.interval and not _stop:
            time.sleep(min(1.0, args.interval - slept))
            slept += 1.0

    print(json.dumps({
        "rounds": rounds,
        "rows_written": rounds * len(symbols),
        "rows_ok": ok_rows,
        "rows_zero_spread": zero,
        "rows_crossed": crossed,
        "rows_stale": stale,
        "server": server,
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
