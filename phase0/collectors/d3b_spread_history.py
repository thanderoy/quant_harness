"""D3b — historical spread census, best-effort.

    python3 -m phase0.collectors.d3b_spread_history --months 12

Pulls tick history per symbol and reduces it to the cost statistics D3
specifies: median and 95th-percentile spread, broken out by session bucket,
plus round-trip cost expressed **as a percentage of 1xATR** at M15, H1 and H4.
That ratio — not basis points of notional — is what decides whether a
mechanism can pay for itself.

Two rules this collector exists to enforce mechanically:

1. **Record the depth actually obtained; never substitute a shorter window.**
   Pepperstone tick retention varies by symbol, and twelve months may simply
   not exist. Silently returning eight months labelled as twelve turns a data
   limitation into a false cost estimate, which then propagates into every
   gate downstream. ``requested_months`` and ``obtained_months`` are both
   recorded per symbol, and a shortfall sets ``depth_shortfall=True`` rather
   than being smoothed over.

2. **A partial pull is not a result.** If no symbol yields usable ticks the
   artifact is written with ``status=BLOCKED`` and a non-zero exit, so an
   empty census cannot be mistaken for a cheap one.

PREREQUISITE — mt5-api does not yet expose tick history
-------------------------------------------------------
As of WMPS 63d93f6 there is no copy_ticks_range endpoint, so this raises
``EndpointMissing`` against a live API. Required addition specified in
``docs/mt5_api_additions.md``. Committed unrun for the same reason as D1.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase0.collectors._client import (
    UNIVERSE,
    EndpointMissing,
    MT5Unavailable,
    get,
    now_iso,
    probe,
    write_artifact,
)
from phase0.collectors.d3a_spread_forward import in_rollover_window, session_bucket

#: Commission per round turn per lot, Pepperstone Razor. HAND_ENTERED — it
#: comes from the account's schedule, not from the terminal, so it carries the
#: same provenance caveat as any seeded value and is stamped as such.
RAZOR_COMMISSION_PER_LOT_ROUND_TURN_USD = 7.0
COMMISSION_PROVENANCE = "HAND_ENTERED"

TIMEFRAMES = ("M15", "H1", "H4")


#: Seconds allowed for one chunk. A month of XAUUSD ticks is millions of rows;
#: the default 15s client timeout is not remotely enough, and a timeout here
#: looks identical to "no history available" unless it is given room to succeed.
CHUNK_TIMEOUT_S = 900.0

#: Spread values are discretised by tick size, so a Counter over rounded
#: spreads is an EXACT representation of the distribution at a fraction of the
#: memory. Holding millions of floats per session bucket per symbol is what
#: made the first run unrunnable; this makes the quantiles exact and cheap.
SPREAD_ROUND_DP = 8


def quantile_from_counter(counter: Counter, q: float) -> float | None:
    """Exact quantile from a value->count histogram."""
    total = sum(counter.values())
    if total == 0:
        return None
    target = q * (total - 1)
    seen = 0
    for value in sorted(counter):
        seen += counter[value]
        if seen > target:
            return value
    return max(counter)


#: Days per chunk. Measured: XAUUSD returns ~780k ticks for 2 days, so a
#: 30-day chunk would be ~11M and would hit the endpoint's 2M row cap and come
#: back truncated. 5 days keeps a chunk under the cap with headroom.
DEFAULT_CHUNK_DAYS = 5


def month_chunks(start: datetime, end: datetime,
                 chunk_days: int = DEFAULT_CHUNK_DAYS) -> list[tuple[datetime, datetime]]:
    """Split a window into fixed-length chunks.

    Chunking is not only about timeouts: it bounds peak memory, keeps each
    response under the row cap so nothing is silently truncated, and means an
    interrupted pull leaves the chunks already processed rather than nothing.
    """
    out = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=chunk_days), end)
        out.append((cursor, nxt))
        cursor = nxt
    return out


def fetch_ticks(symbol: str, start: datetime, end: datetime) -> tuple[list[dict], bool]:
    res = get("/api/v1/ticks", {
        "symbol": symbol,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
    }, timeout=CHUNK_TIMEOUT_S)
    payload = res.payload
    if isinstance(payload, list):
        return list(payload), False
    return list(payload.get("ticks", [])), bool(payload.get("truncated", False))


class SymbolAccumulator:
    """Streaming spread statistics for one symbol.

    Accumulates histograms rather than raw ticks so a twelve-month pull stays
    within memory. Exactness is preserved because spreads are discretised.
    """

    def __init__(self) -> None:
        self.by_session: dict[str, Counter] = {}
        self.rollover: Counter = Counter()
        self.overall: Counter = Counter()
        self.n_returned = 0
        self.n_parsed = 0
        self.n_nonpositive = 0
        self.first_ts: datetime | None = None
        self.last_ts: datetime | None = None
        self.truncated_chunks = 0

    def add(self, ticks: list[dict], truncated: bool) -> None:
        if truncated:
            self.truncated_chunks += 1
        self.n_returned += len(ticks)
        for t in ticks:
            try:
                bid, ask = float(t["bid"]), float(t["ask"])
                ts = datetime.fromisoformat(str(t["time"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self.n_parsed += 1
            if self.first_ts is None or ts < self.first_ts:
                self.first_ts = ts
            if self.last_ts is None or ts > self.last_ts:
                self.last_ts = ts

            spread = round(ask - bid, SPREAD_ROUND_DP)
            if spread <= 0:
                # Counted, not dropped: the rate is a data-quality signal, and
                # a non-positive spread was never quotable so it must not enter
                # the distribution the cost estimate is taken from.
                self.n_nonpositive += 1
                continue
            self.by_session.setdefault(session_bucket(ts), Counter())[spread] += 1
            self.overall[spread] += 1
            if in_rollover_window(ts):
                self.rollover[spread] += 1

    @staticmethod
    def _stats(c: Counter) -> dict:
        return {
            "n": sum(c.values()),
            "median_spread": quantile_from_counter(c, 0.5),
            "p95_spread": quantile_from_counter(c, 0.95),
        }

    def result(self) -> dict:
        return {
            "n_ticks_returned": self.n_returned,
            "n_ticks_parsed": self.n_parsed,
            "n_nonpositive_spreads_excluded": self.n_nonpositive,
            "chunks_truncated": self.truncated_chunks,
            "by_session": {s: self._stats(c)
                           for s, c in sorted(self.by_session.items())},
            "rollover_window": self._stats(self.rollover),
            "overall": self._stats(self.overall),
        }


def cost_as_pct_of_atr(median_spread: float | None, atr_by_tf: dict) -> dict:
    """Round-trip cost as a percentage of 1xATR, per timeframe.

    Round trip is one spread paid on entry and one on exit, plus commission.
    Commission is left out of the price-unit ratio here because it is charged
    per lot, not per price unit; it is reported separately and combined once
    D1 gives contract size. Reporting a half-complete ratio as if it were the
    whole cost is the failure mode this split avoids.
    """
    if median_spread is None:
        return {tf: None for tf in TIMEFRAMES}
    round_trip = 2.0 * median_spread
    return {
        tf: (100.0 * round_trip / atr) if atr else None
        for tf, atr in atr_by_tf.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", type=int, default=12,
                    help="requested history depth (default 12)")
    ap.add_argument("--symbols", nargs="*", default=list(UNIVERSE))
    ap.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS,
                    help=f"days per request (default {DEFAULT_CHUNK_DAYS})")
    ap.add_argument("--atr", type=str, default="",
                    help='JSON of {symbol: {M15: x, H1: y, H4: z}} median ATR, '
                         'from D2. Omitted -> ATR ratios reported as null.')
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="directory for the artifact (default: phase0/)")
    ap.add_argument("--max-consecutive-failures", type=int, default=10,
                    help="abort the run after this many consecutive chunk "
                         "fetches fail as unreachable (default 10)")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30 * args.months)
    atr_map = json.loads(args.atr) if args.atr else {}

    artifact: dict = {
        "task": "D3b",
        "collected_at_utc": now_iso(),
        "requested_months": args.months,
        "window_requested": {"from": start.isoformat(), "to": end.isoformat()},
        "commission_per_lot_round_turn_usd": RAZOR_COMMISSION_PER_LOT_ROUND_TURN_USD,
        "commission_provenance": COMMISSION_PROVENANCE,
        "probe": probe(),
    }

    if not artifact["probe"]["reachable"]:
        artifact["status"] = "BLOCKED"
        artifact["blocked_reason"] = artifact["probe"]["error"]
        path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact, args.out_dir)
        print(f"BLOCKED — {artifact['blocked_reason']}", file=sys.stderr)
        print(f"artifact: {path}")
        return 2

    per_symbol: dict[str, dict] = {}
    errors: dict[str, str] = {}
    chunks = month_chunks(start, end, args.chunk_days)
    artifact["n_chunks_per_symbol"] = len(chunks)

    # A hole in one chunk is transient; a source that has gone away answers
    # nothing, ever. Without this bound the 2026-09-01 run ground through 7
    # symbols x 72 chunks of connection-refused before reporting.
    max_consecutive = args.max_consecutive_failures
    consecutive_unavailable = 0
    aborted_reason: str | None = None

    for sym in args.symbols:
        if aborted_reason:
            errors[sym] = f"not attempted: {aborted_reason}"
            continue
        acc = SymbolAccumulator()
        chunk_errors: list[str] = []
        for c_start, c_end in chunks:
            try:
                ticks, truncated = fetch_ticks(sym, c_start, c_end)
            except EndpointMissing as exc:
                artifact["status"] = "BLOCKED"
                artifact["blocked_reason"] = str(exc)
                artifact["dependency"] = (
                    "mt5-api must expose GET /api/v1/ticks (copy_ticks_range) — "
                    "see docs/mt5_api_additions.md"
                )
                path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact, args.out_dir)
                print(f"BLOCKED — {exc}", file=sys.stderr)
                print(f"artifact: {path}")
                return 3
            except MT5Unavailable as exc:
                # One failed chunk is a hole in the window, not a dead symbol.
                # Recorded so obtained depth is not overstated.
                chunk_errors.append(f"{c_start.date()}..{c_end.date()}: {exc}")
                consecutive_unavailable += 1
                if consecutive_unavailable >= max_consecutive:
                    aborted_reason = (
                        f"source unreachable for {consecutive_unavailable} "
                        f"consecutive chunks: {exc}"
                    )
                    break
                continue
            consecutive_unavailable = 0
            acc.add(ticks, truncated)
            print(f"  {sym} {c_start.date()}..{c_end.date()}: "
                  f"{len(ticks)} ticks", file=sys.stderr)

        if acc.n_parsed == 0:
            errors[sym] = ("; ".join(chunk_errors) or "no ticks returned")
            continue

        stats = acc.result()
        obtained_days = ((acc.last_ts - acc.first_ts).days
                         if acc.first_ts and acc.last_ts else 0)
        obtained_months = round(obtained_days / 30.0, 2)
        stats.update({
            "requested_months": args.months,
            "obtained_months": obtained_months,
            "obtained_from": acc.first_ts.isoformat() if acc.first_ts else None,
            "obtained_to": acc.last_ts.isoformat() if acc.last_ts else None,
            # The load-bearing flag: a short window is reported as short.
            "depth_shortfall": obtained_months < args.months * 0.95,
            "failed_chunks": chunk_errors,
        })
        stats["round_trip_cost_pct_of_atr"] = cost_as_pct_of_atr(
            stats["overall"]["median_spread"], atr_map.get(sym, {}),
        )
        per_symbol[sym] = stats

        # Written after every symbol, not once at the end: a multi-hour pull
        # that is interrupted must leave the symbols already done rather than
        # nothing at all.
        artifact["per_symbol"] = per_symbol
        artifact["errors"] = errors
        artifact["status"] = "IN_PROGRESS"
        write_artifact(f"d3b_spread_history_{stamp}.json", artifact, args.out_dir)
        print(f"  [{sym}] done — {stats['overall']['n']} spreads, "
              f"median {stats['overall']['median_spread']}", file=sys.stderr)

    artifact["per_symbol"] = per_symbol
    artifact["errors"] = errors

    shortfalls = [s for s, v in per_symbol.items() if v["depth_shortfall"]]
    artifact["depth_shortfalls"] = shortfalls

    # Checked before the empty-result case: if the source died mid-run, that is
    # why there is nothing here. Reporting BLOCKED instead would point at a
    # dependency or code fault and send the next reader to the wrong place.
    if aborted_reason:
        artifact["status"] = "ABORTED_SOURCE_UNREACHABLE"
        artifact["aborted_reason"] = aborted_reason
        rc = 2
    elif not per_symbol:
        artifact["status"] = "BLOCKED"
        artifact["blocked_reason"] = "no symbol returned usable tick history"
        rc = 1
    elif errors or shortfalls:
        artifact["status"] = "PARTIAL_HISTORY"
        rc = 1
    else:
        artifact["status"] = "OK"
        rc = 0

    path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact, args.out_dir)
    print(json.dumps({
        "status": artifact["status"],
        "n_symbols": len(per_symbol),
        "depth_shortfalls": shortfalls,
        "errors": list(errors),
        "aborted_reason": aborted_reason,
        "artifact": str(path),
    }, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
