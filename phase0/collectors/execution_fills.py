"""Execution fills — every live deal, with the quote that stood when it filled.

    python3 -m phase0.collectors.execution_fills --expect-server Pepperstone \
        --date-from 2025-01-01 --date-to 2026-10-12 --out-dir /out

Slip was the last cost input with no source (``SlipModel`` HAND_ENTERED at one
tick). Only a real fill can measure it, so this reads the account's real fills.
**Read-only by construction**: it issues GETs to ``/api/v1/account``,
``/api/v1/symbol_info``, ``/api/v1/deals`` and ``/api/v1/ticks`` and nothing
else. It never touches an order or position endpoint.

A deal carries its fill price but not the price that was requested, so classic
slip (fill minus requested) is not available. What this records instead, per
trade deal, is the tick stream around the fill: the last quote in a strictly
earlier second (``pre``), the quotes inside the fill's own second (``same``),
and the first quote after it (``post``). ``/api/v1/ticks`` returns times to
the second only, so a tick in the fill's own second may be before or after the
fill; ``pre`` is the quote that unambiguously stood before it.

Deal times and tick times are both MT5 server-clock epochs, so they are
compared directly. That is an assumption the analysis verifies rather than
trusts: a fill that sits at the touch of the ``pre`` quote to the tick is only
possible when the clocks agree (see ``research.datasets.execution_cost``).

Output is two files:

``execution_fills_raw_<UTC>.json``
    One record per trade deal. **Gitignored** — it is a per-fill dump of a
    real-money account. It carries no ticket, order, position, magic, comment,
    login or name: only symbol, side, entry/exit leg, reason code, volume,
    fill price, fill time and the surrounding quotes.
``execution_fills_<UTC>.json``
    The run record: broker context, window, counts, tick sizes, failures.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
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

#: MT5 deal types that are trades. Everything else (balance, credit, ...) is
#: bookkeeping and has no market price.
DEAL_TYPE_SIDE = {0: "BUY", 1: "SELL"}
DEAL_ENTRY = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}
DEAL_REASON = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL",
               5: "TP", 6: "SO", 7: "ROLLOVER", 8: "VMARGIN", 9: "SPLIT"}

#: Tick window around each fill. Wide enough that a quiet market still has a
#: quote before the fill; the analysis reports how stale ``pre`` was.
LOOKBACK_S = 120
LOOKAHEAD_S = 10

#: The fields kept from a deal. Identity fields are dropped here, at the
#: boundary, so no downstream step can leak them.
KEPT = ("symbol", "volume", "price", "time_msc")


def _iso(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S")


def _tick_epoch(t: str) -> int:
    return int(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp())


def trade_deals(deals: list[dict]) -> list[dict]:
    """Strip identity and keep only priced trade deals."""
    out = []
    for d in deals:
        if d.get("type") not in DEAL_TYPE_SIDE or not d.get("symbol"):
            continue
        rec = {k: d[k] for k in KEPT}
        rec["side"] = DEAL_TYPE_SIDE[d["type"]]
        rec["entry"] = DEAL_ENTRY.get(d.get("entry"), f"UNKNOWN_{d.get('entry')}")
        rec["reason"] = DEAL_REASON.get(d.get("reason"), f"UNKNOWN_{d.get('reason')}")
        out.append(rec)
    return sorted(out, key=lambda r: r["time_msc"])


def quotes_around(ticks: list[dict], fill_epoch_s: int) -> dict:
    """Split a tick window into the quote before, during and after a fill."""
    pre = same_first = same_last = post = None
    n_same = 0
    for t in ticks:
        if not t.get("bid") or not t.get("ask"):
            continue
        e = _tick_epoch(t["time"])
        q = {"t": e, "bid": t["bid"], "ask": t["ask"]}
        if e < fill_epoch_s:
            pre = q
        elif e == fill_epoch_s:
            n_same += 1
            same_first = same_first or q
            same_last = q
        elif post is None:
            post = q
    return {"pre": pre, "same_first": same_first, "same_last": same_last,
            "n_same": n_same, "post": post}


def collect(date_from: str, date_to: str) -> tuple[list[dict], dict, list[dict]]:
    deals = get("/api/v1/deals", {"date_from": date_from, "date_to": date_to},
                timeout=120).payload
    fills = trade_deals(deals if isinstance(deals, list) else [])
    tick_size = {}
    for sym in sorted({f["symbol"] for f in fills}):
        info = get("/api/v1/symbol_info", {"symbol": sym}).payload
        tick_size[sym] = {"tick_size": info.get("tick_size"),
                          "digits": info.get("digits")}
    failures = []
    for f in fills:
        fill_s = f["time_msc"] // 1000
        try:
            res = get("/api/v1/ticks", {
                "symbol": f["symbol"],
                "date_from": _iso(fill_s - LOOKBACK_S),
                "date_to": _iso(fill_s + LOOKAHEAD_S)}, timeout=60).payload
            f["quotes"] = quotes_around(res.get("ticks", []), fill_s)
        except MT5Unavailable as exc:
            f["quotes"] = None
            failures.append({"symbol": f["symbol"], "error": str(exc)})
    return fills, tick_size, failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--expect-server", default=None)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run: dict = {"task": "execution_fills", "collected_at_utc": now_iso(),
                 "window": [args.date_from, args.date_to],
                 "tick_window_s": [-LOOKBACK_S, LOOKAHEAD_S],
                 "broker": broker_context()}
    mismatch = server_mismatch(run["broker"], args.expect_server)
    if mismatch:
        run.update(status="REFUSED_SERVER_MISMATCH", blocked_reason=mismatch)
        write_artifact(f"execution_fills_{stamp}.json", run, args.out_dir)
        print(f"REFUSED — {mismatch}", file=sys.stderr)
        return 4
    try:
        fills, tick_size, failures = collect(args.date_from, args.date_to)
    except (MT5Unavailable, EndpointMissing) as exc:
        run.update(status="BLOCKED", blocked_reason=str(exc))
        write_artifact(f"execution_fills_{stamp}.json", run, args.out_dir)
        print(f"BLOCKED — {exc}", file=sys.stderr)
        return 2
    run.update(n_trade_deals=len(fills), tick_size=tick_size,
               tick_failures=failures,
               status="PARTIAL" if failures else "OK")
    if fills:
        run["span"] = [_iso(fills[0]["time_msc"] / 1000)[:10],
                       _iso(fills[-1]["time_msc"] / 1000)[:10]]
    write_artifact(f"execution_fills_raw_{stamp}.json",
                   {"run": run, "fills": fills}, args.out_dir)
    path = write_artifact(f"execution_fills_{stamp}.json", run, args.out_dir)
    print(f"{run['status']} — {len(fills)} trade deals — {path}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
