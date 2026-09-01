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
import statistics
import sys
from datetime import datetime, timedelta, timezone

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


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(int(q * (len(s) - 1)), len(s) - 1)
    return s[idx]


def fetch_ticks(symbol: str, start: datetime, end: datetime) -> list[dict]:
    res = get("/api/v1/ticks", {
        "symbol": symbol,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
    })
    payload = res.payload
    return list(payload) if isinstance(payload, list) else list(payload.get("ticks", []))


def reduce_symbol(symbol: str, ticks: list[dict]) -> dict:
    """Collapse a tick stream into per-session spread statistics."""
    by_session: dict[str, list[float]] = {}
    rollover: list[float] = []
    parsed = 0
    for t in ticks:
        try:
            bid, ask = float(t["bid"]), float(t["ask"])
            ts = datetime.fromisoformat(str(t["time"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        spread = ask - bid
        parsed += 1
        by_session.setdefault(session_bucket(ts), []).append(spread)
        if in_rollover_window(ts):
            rollover.append(spread)

    out = {
        "n_ticks_returned": len(ticks),
        "n_ticks_parsed": parsed,
        "by_session": {
            s: {
                "n": len(v),
                "median_spread": statistics.median(v) if v else None,
                "p95_spread": pct(v, 0.95),
            }
            for s, v in sorted(by_session.items())
        },
        "rollover_window": {
            "n": len(rollover),
            "median_spread": statistics.median(rollover) if rollover else None,
            "p95_spread": pct(rollover, 0.95),
        },
    }
    all_spreads = [x for v in by_session.values() for x in v]
    out["overall"] = {
        "n": len(all_spreads),
        "median_spread": statistics.median(all_spreads) if all_spreads else None,
        "p95_spread": pct(all_spreads, 0.95),
    }
    return out


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
    ap.add_argument("--atr", type=str, default="",
                    help='JSON of {symbol: {M15: x, H1: y, H4: z}} median ATR, '
                         'from D2. Omitted -> ATR ratios reported as null.')
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
        path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact)
        print(f"BLOCKED — {artifact['blocked_reason']}", file=sys.stderr)
        print(f"artifact: {path}")
        return 2

    per_symbol: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for sym in args.symbols:
        try:
            ticks = fetch_ticks(sym, start, end)
        except EndpointMissing as exc:
            artifact["status"] = "BLOCKED"
            artifact["blocked_reason"] = str(exc)
            artifact["dependency"] = (
                "mt5-api must expose GET /api/v1/ticks (copy_ticks_range) — "
                "see docs/mt5_api_additions.md"
            )
            path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact)
            print(f"BLOCKED — {exc}", file=sys.stderr)
            print(f"artifact: {path}")
            return 3
        except MT5Unavailable as exc:
            errors[sym] = str(exc)
            continue

        stats = reduce_symbol(sym, ticks)
        times = []
        for t in ticks:
            try:
                times.append(datetime.fromisoformat(
                    str(t["time"]).replace("Z", "+00:00")))
            except (KeyError, TypeError, ValueError):
                continue
        obtained_days = ((max(times) - min(times)).days if len(times) > 1 else 0)
        obtained_months = round(obtained_days / 30.0, 2)
        stats.update({
            "requested_months": args.months,
            "obtained_months": obtained_months,
            "obtained_from": min(times).isoformat() if times else None,
            "obtained_to": max(times).isoformat() if times else None,
            # The load-bearing flag: a short window is reported as short.
            "depth_shortfall": obtained_months < args.months * 0.95,
        })
        stats["round_trip_cost_pct_of_atr"] = cost_as_pct_of_atr(
            stats["overall"]["median_spread"], atr_map.get(sym, {}),
        )
        per_symbol[sym] = stats

    artifact["per_symbol"] = per_symbol
    artifact["errors"] = errors

    shortfalls = [s for s, v in per_symbol.items() if v["depth_shortfall"]]
    artifact["depth_shortfalls"] = shortfalls

    if not per_symbol:
        artifact["status"] = "BLOCKED"
        artifact["blocked_reason"] = "no symbol returned usable tick history"
        rc = 1
    elif errors or shortfalls:
        artifact["status"] = "PARTIAL_HISTORY"
        rc = 1
    else:
        artifact["status"] = "OK"
        rc = 0

    path = write_artifact(f"d3b_spread_history_{stamp}.json", artifact)
    print(json.dumps({
        "status": artifact["status"],
        "n_symbols": len(per_symbol),
        "depth_shortfalls": shortfalls,
        "errors": list(errors),
        "artifact": str(path),
    }, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
