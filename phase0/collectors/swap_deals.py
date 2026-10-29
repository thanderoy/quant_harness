"""Swap deals — every closed live position, with the swap it was charged.

    python3 -m phase0.collectors.swap_deals --expect-server Pepperstone \
        --date-from 2025-01-01 --date-to 2026-10-30 --out-dir /out

Swap is the last cost input with no source: ``PEPPERSTONE_XAUUSD_SWAP_*`` are
placeholders, and the registry snapshots read ``swap_long``/``swap_short`` as
0.0 for most symbols, cause unknown. A booked swap on a real position is a
measurement that does not depend on what ``symbol_info`` reports.

**Read-only by construction**: it issues GETs to ``/api/v1/account``,
``/api/v1/symbol_info`` and ``/api/v1/deals`` and nothing else.

MT5 books a position's accumulated swap on its closing deal, so deals are
grouped by ``position_id`` here, at the boundary, and the id is dropped once
the grouping is done. Each record carries symbol, side, lots, open and close
time (server-clock epoch seconds) and the summed swap and profit — no ticket,
order, position, magic, comment, login or name.

Output is two files:

``swap_deals_raw_<UTC>.json``
    One record per closed position. **Gitignored** — it is a per-position dump
    of a real-money account.
``swap_deals_<UTC>.json``
    The run record: broker context, window, counts, and the ``symbol_info``
    swap fields as the terminal reports them now, for comparison.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from phase0.collectors._client import (
    EndpointMissing,
    MT5Unavailable,
    broker_context,
    get,
    now_iso,
    server_mismatch,
    write_artifact,
)

DEAL_TYPE_SIDE = {0: "BUY", 1: "SELL"}
#: DEAL_ENTRY_IN. Every other entry value closes (OUT, INOUT, OUT_BY).
ENTRY_IN = 0
SWAP_FIELDS = ("swap_mode", "swap_long", "swap_short")


def positions(deals: list[dict]) -> tuple[list[dict], dict]:
    """Group trade deals into closed positions and strip identity.

    Returns the positions, oldest first, and counts of what was left out: a
    position with no opening deal in the window, or one still open at its end.
    """
    by_pos: dict[int, list[dict]] = defaultdict(list)
    for d in deals:
        if d.get("type") in DEAL_TYPE_SIDE and d.get("symbol"):
            by_pos[d.get("position_id", 0)].append(d)
    out, skipped = [], {"no_open_in_window": 0, "still_open": 0}
    for legs in by_pos.values():
        legs.sort(key=lambda d: d["time_msc"])
        opens = [d for d in legs if d.get("entry") == ENTRY_IN]
        closes = [d for d in legs if d.get("entry") != ENTRY_IN]
        if not opens:
            skipped["no_open_in_window"] += 1
            continue
        if not closes:
            skipped["still_open"] += 1
            continue
        out.append({
            "symbol": opens[0]["symbol"],
            "side": DEAL_TYPE_SIDE[opens[0]["type"]],
            "lots": sum(d["volume"] for d in opens),
            "open_s": opens[0]["time_msc"] // 1000,
            "close_s": closes[-1]["time_msc"] // 1000,
            "swap": round(sum(d.get("swap", 0.0) for d in legs), 2),
            "profit": round(sum(d.get("profit", 0.0) for d in legs), 2),
        })
    return sorted(out, key=lambda p: p["open_s"]), skipped


def collect(date_from: str, date_to: str) -> tuple[list[dict], dict, dict]:
    deals = get("/api/v1/deals", {"date_from": date_from, "date_to": date_to},
                timeout=120).payload
    pos, skipped = positions(deals if isinstance(deals, list) else [])
    swap_info = {}
    for sym in sorted({p["symbol"] for p in pos}):
        info = get("/api/v1/symbol_info", {"symbol": sym}).payload
        swap_info[sym] = {k: info.get(k) for k in SWAP_FIELDS}
    return pos, skipped, swap_info


def _iso(epoch_s: int) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--expect-server", default=None)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run: dict = {"task": "swap_deals", "collected_at_utc": now_iso(),
                 "window": [args.date_from, args.date_to],
                 "broker": broker_context()}
    mismatch = server_mismatch(run["broker"], args.expect_server)
    if mismatch:
        run.update(status="REFUSED_SERVER_MISMATCH", blocked_reason=mismatch)
        write_artifact(f"swap_deals_{stamp}.json", run, args.out_dir)
        print(f"REFUSED — {mismatch}", file=sys.stderr)
        return 4
    try:
        pos, skipped, swap_info = collect(args.date_from, args.date_to)
    except (MT5Unavailable, EndpointMissing) as exc:
        run.update(status="BLOCKED", blocked_reason=str(exc))
        write_artifact(f"swap_deals_{stamp}.json", run, args.out_dir)
        print(f"BLOCKED — {exc}", file=sys.stderr)
        return 2
    run.update(status="OK", n_positions=len(pos), skipped=skipped,
               n_nonzero_swap=sum(1 for p in pos if p["swap"]),
               symbol_info_swap=swap_info)
    if pos:
        run["span"] = [_iso(pos[0]["open_s"]), _iso(pos[-1]["close_s"])]
    write_artifact(f"swap_deals_raw_{stamp}.json",
                   {"run": run, "positions": pos}, args.out_dir)
    path = write_artifact(f"swap_deals_{stamp}.json", run, args.out_dir)
    print(f"OK — {len(pos)} positions, {run['n_nonzero_swap']} with swap — {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
