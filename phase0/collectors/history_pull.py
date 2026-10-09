"""Pull OHLCV history from mt5-api into the house CSV format.

    python3 -m phase0.collectors.history_pull --symbols GER40 UK100 \
        --out-dir /out --expect-server Pepperstone

Writes ``<SYMBOL>_<TF>.csv`` (``Date;Open;High;Low;Close;Volume``, server time,
``%Y.%m.%d %H:%M``, tick volume) and one ``history_pull_<UTC>.json`` artifact
naming the trade server, the page geometry and what was dropped.

The seq=73 pulls were done by hand and validated only on install, after a
first attempt left a truncated XAGUSD file that a naive length check would
have passed. This makes the pull a committed step with its own record. It
checks the file's *shape* — monotonic, unique, well-formed rows. Whether the
series is the timeframe it claims, and where its gaps are, is
``research.admission``'s job, run before anything enters a universe.

The endpoint pages backwards: ``start_pos`` counts bars back from the newest.
Once a first page has succeeded, a 404 on a later page means the terminal has
no history that far back, not a missing endpoint, and ends the pull.
"""

from __future__ import annotations

import argparse
import sys
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

PAGE = 10_000
#: Safety stop. XAGUSD hit a 99,999-bar cap at seq=73; nothing here needs more.
MAX_PAGES = 30
HEADER = "Date;Open;High;Low;Close;Volume"


def fetch_pages(symbol: str, timeframe: str, page: int = PAGE,
                max_pages: int = MAX_PAGES) -> tuple[list[dict], int]:
    """Every bar the terminal will serve, oldest first, newest bar dropped.

    The newest bar is still forming when the pull runs, so it is removed
    rather than written as if it had closed.
    """
    by_time: dict[str, dict] = {}
    pages = 0
    for k in range(max_pages):
        params = {"symbol": symbol, "timeframe": timeframe,
                  "count": page, "start_pos": k * page}
        try:
            rows = get("/api/v1/rates", params, timeout=120).payload.get("rates", [])
        except EndpointMissing:
            if k == 0:
                raise
            break
        pages += 1
        for r in rows:
            by_time[r["time"]] = r
        if len(rows) < page:
            break
    bars = [by_time[t] for t in sorted(by_time)]
    return bars[:-1], pages


def validate(bars: list[dict]) -> list[str]:
    """Shape problems that make a file unsafe to write. Empty means none."""
    problems = []
    if len(bars) < 1000:
        problems.append(f"only {len(bars)} bars")
    times = [b["time"] for b in bars]
    if times != sorted(set(times)):
        problems.append("times not strictly increasing")
    for b in bars:
        if any(b.get(k) is None for k in ("open", "high", "low", "close")):
            problems.append(f"missing price at {b.get('time')}")
            break
    return problems


def to_csv(bars: list[dict]) -> str:
    lines = [HEADER]
    for b in bars:
        t = datetime.fromisoformat(b["time"]).strftime("%Y.%m.%d %H:%M")
        lines.append(f"{t};{b['open']};{b['high']};{b['low']};{b['close']};"
                     f"{int(b.get('tick_volume') or 0)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--timeframe", default="H1")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--expect-server", default=None)
    ap.add_argument("--page", type=int, default=PAGE)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact: dict = {"task": "history_pull", "collected_at_utc": now_iso(),
                      "timeframe": args.timeframe, "page": args.page,
                      "broker": broker_context(), "symbols": {}}
    mismatch = server_mismatch(artifact["broker"], args.expect_server)
    if mismatch:
        artifact["status"] = "REFUSED_SERVER_MISMATCH"
        artifact["blocked_reason"] = mismatch
        write_artifact(f"history_pull_{stamp}.json", artifact, args.out_dir)
        print(f"REFUSED — {mismatch}", file=sys.stderr)
        return 4

    failed = False
    for sym in args.symbols:
        try:
            bars, pages = fetch_pages(sym, args.timeframe, args.page)
        except (MT5Unavailable, EndpointMissing) as exc:
            artifact["symbols"][sym] = {"status": "ERROR", "error": str(exc)}
            failed = True
            continue
        problems = validate(bars)
        entry = {"pages": pages, "n_bars": len(bars),
                 "dropped_forming_bar": True, "problems": problems}
        if bars:
            entry.update(first=bars[0]["time"], last=bars[-1]["time"])
        if problems:
            entry["status"] = "REFUSED"
            failed = True
        else:
            path = args.out_dir / f"{sym}_{args.timeframe}.csv"
            path.write_text(to_csv(bars))
            entry.update(status="OK", file=path.name)
        artifact["symbols"][sym] = entry

    artifact["status"] = "PARTIAL" if failed else "OK"
    path = write_artifact(f"history_pull_{stamp}.json", artifact, args.out_dir)
    print(f"{artifact['status']} — artifact: {path}")
    for sym, e in artifact["symbols"].items():
        print(f"  {sym}: {e.get('status')} {e.get('n_bars', '')} "
              f"{e.get('first', '')}..{e.get('last', '')} {e.get('problems', '')}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
