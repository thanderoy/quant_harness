"""Distil the D3b tick-history artifact into a committed spread snapshot.

D3b's raw output is gitignored — it is a ~100M-tick summary keyed by a
timestamped filename that only exists on the machine that ran the collector.
The fill frontier needs the *statistics* in CI, so this reduces D3b to the
few numbers ``resources.execution`` consumes and stamps them with where they
came from.

Run from the repo root::

    python -m phase0.build_d3_spread_snapshot

It refuses to invent: symbols absent from D3b are absent from the snapshot,
and :class:`resources.execution.spreads.SpreadSnapshot` raises for them
rather than defaulting to a zero spread.
"""

from __future__ import annotations

import glob
import json
import pathlib
import sys

OUT = (pathlib.Path(__file__).resolve().parents[1] / "packages" / "qh-resources"
       / "resources" / "execution" / "snapshots")


def build(source: pathlib.Path) -> dict:
    d = json.loads(source.read_text())
    if d.get("status") != "OK":
        raise SystemExit(f"{source.name}: status is {d.get('status')!r}, not OK")

    symbols = {}
    for symbol, s in d["per_symbol"].items():
        overall = s["overall"]
        symbols[symbol] = {
            "median_spread": overall["median_spread"],
            "p95_spread": overall["p95_spread"],
            "n_ticks": overall["n"],
            "obtained_months": s.get("obtained_months"),
            "zero_spread_fraction": s.get("zero_spread_fraction"),
            "by_session": {
                name: {"median_spread": v["median_spread"],
                       "p95_spread": v["p95_spread"], "n_ticks": v["n"]}
                for name, v in s.get("by_session", {}).items()
            },
        }

    broker = d.get("broker", {})
    return {
        "snapshot_id": f"d3b_{d['collected_at_utc'][:10].replace('-', '')}",
        "as_of_utc": d["collected_at_utc"],
        "provenance": "MEASURED",
        "task": "D3b",
        "source_artifact": source.name,
        "broker": broker.get("server", "UNKNOWN"),
        "account_currency": broker.get("currency"),
        "window_requested": d.get("window_requested"),
        "note": ("Spreads are full bid-ask widths in price units, measured "
                 "from copy_ticks_range. Consumers charge half to each side."),
        "symbols": symbols,
    }


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    candidates = sorted(glob.glob(str(root / "phase0"
                                      / "d3b_spread_history_*.json")))
    if not candidates:
        print("no D3b artifact found; nothing to build", file=sys.stderr)
        return 1
    source = pathlib.Path(candidates[-1])
    snapshot = build(source)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"spreads_{snapshot['snapshot_id']}.json"
    dest.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"{source.name} -> {dest.relative_to(root)} "
          f"({len(snapshot['symbols'])} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
