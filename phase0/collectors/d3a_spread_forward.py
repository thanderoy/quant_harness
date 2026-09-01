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


def sample_once(symbols: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    for sym in symbols:
        ts = datetime.now(timezone.utc)
        row: dict = {
            "symbol": sym,
            "sampled_at_utc": ts.isoformat(),
            "session": session_bucket(ts),
            "rollover_window": in_rollover_window(ts),
        }
        try:
            payload = get("/api/v1/tick", {"symbol": sym}).payload
            bid = float(payload["bid"])
            ask = float(payload["ask"])
            row.update({
                "bid": bid,
                "ask": ask,
                "spread": ask - bid,
                "tick_time": payload.get("time"),
                "ok": True,
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
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    symbols = tuple(args.symbols)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rounds = 0
    ok_rows = 0
    while not _stop:
        rows = sample_once(symbols)
        append(args.out, rows)
        rounds += 1
        ok_rows += sum(1 for r in rows if r.get("ok"))
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
        "out": str(args.out),
        "stopped_at_utc": now_iso(),
    }, indent=2))
    return 0 if ok_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
