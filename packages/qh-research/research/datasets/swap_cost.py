"""research.datasets.swap_cost — overnight swap measured from live positions.

Reduces the per-position dump written by ``phase0.collectors.swap_deals`` to
per-symbol, per-side aggregates. The dump stays out of the repo; only what this
module returns is committed.

Two sources, kept apart because they answer different questions.

``booked`` — the swap actually charged on closed positions
    What the account paid, at the rates in force when the positions were held.
    Each position's swap is divided by its lots and by its rollover *units*:
    one per server-clock midnight crossed that ends a weekday, three for the
    triple-swap weekday. Deal times are server-clock epochs, so the midnight
    counted is the server's. The rollover convention is checked rather than
    assumed: every position crossing one should be charged and no other, and
    the triple-day ratio should come out near 3.

``quoted`` — ``symbol_info`` swap fields on the day of collection
    What the terminal charges now. Rates move with interest-rate differentials
    and are reset by the broker weekly, so this is a dated point, not a
    constant. ``swap_mode`` 1 (points) is converted to USD per lot per night as
    points x point / tick_size x tick_value, which for every symbol here is
    the point count itself.

Sign convention: MT5's. Negative is a charge, positive a credit.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: Pepperstone's triple-swap day for FX and metals (Mon=0).
TRIPLE_WEEKDAY = 2
#: ``SYMBOL_SWAP_MODE_POINTS``. The only mode the reduction converts.
SWAP_MODE_POINTS = 1


def rollover_units(open_s: int, close_s: int,
                   triple_weekday: int = TRIPLE_WEEKDAY) -> tuple[int, int]:
    """Rollovers between two server-clock epochs, as (units, nights).

    A rollover is a server midnight ending Monday-Friday; the one ending
    ``triple_weekday`` counts three units.
    """
    day = datetime.fromtimestamp(open_s, timezone.utc).replace(
        hour=0, minute=0, second=0) + timedelta(days=1)
    end = datetime.fromtimestamp(close_s, timezone.utc)
    units = nights = 0
    while day <= end:
        ended = (day - timedelta(days=1)).weekday()
        if ended < 5:
            nights += 1
            units += 3 if ended == triple_weekday else 1
        day += timedelta(days=1)
    return units, nights


def _day(epoch_s: int) -> str:
    return datetime.fromtimestamp(epoch_s, timezone.utc).strftime("%Y-%m-%d")


def booked(positions: list[dict]) -> dict:
    """Per symbol and side, the swap charged per lot per rollover unit."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    crossed_uncharged = charged_uncrossed = 0
    for p in positions:
        units, nights = rollover_units(p["open_s"], p["close_s"])
        if nights and not p["swap"]:
            crossed_uncharged += 1
        if p["swap"] and not nights:
            charged_uncrossed += 1
        if nights and p["swap"]:
            groups[(p["symbol"], p["side"])].append(
                {**p, "units": units, "nights": nights,
                 "per_lot_unit": p["swap"] / p["lots"] / units})
    out = {}
    for (sym, side), rows in sorted(groups.items()):
        out.setdefault(sym, {})[side] = {
            "n": len(rows),
            "median_usd_per_lot_night": round(
                statistics.median(r["per_lot_unit"] for r in rows), 2),
            "span": [_day(min(r["open_s"] for r in rows)),
                     _day(max(r["close_s"] for r in rows))],
        }
    return {"by_symbol": out,
            "n_crossed_rollover": sum(len(v) for v in groups.values())
            + crossed_uncharged,
            "crossed_but_uncharged": crossed_uncharged,
            "charged_but_not_crossed": charged_uncrossed,
            "triple_day_ratio": triple_day_ratio(groups)}


def triple_day_ratio(groups: dict[tuple[str, str], list[dict]]) -> dict:
    """Swap per lot on a triple-day night over a plain night, per group.

    Only single-night positions, so each is one rollover. A ratio near 3
    confirms ``TRIPLE_WEEKDAY``; near 1 would mean the triple falls elsewhere.
    """
    out = {}
    for (sym, side), rows in sorted(groups.items()):
        single = [r for r in rows if r["nights"] == 1]
        triple = [r["swap"] / r["lots"] for r in single if r["units"] == 3]
        plain = [r["swap"] / r["lots"] for r in single if r["units"] == 1]
        if triple and plain and statistics.median(plain):
            out[f"{sym}_{side}"] = round(
                statistics.median(triple) / statistics.median(plain), 2)
    return out


def quoted(swap_info: dict, specs: dict) -> dict:
    """``symbol_info`` swaps as USD per lot per night, where convertible."""
    out = {}
    for sym, s in sorted(swap_info.items()):
        spec = specs.get(sym)
        if s["swap_mode"] != SWAP_MODE_POINTS or spec is None:
            out[sym] = {"converted": False, **s}
            continue
        usd_per_point = (10 ** -spec["digits"]) / spec["tick_size"] \
            * spec["tick_value"]
        out[sym] = {"converted": True,
                    "BUY": round(s["swap_long"] * usd_per_point, 2),
                    "SELL": round(s["swap_short"] * usd_per_point, 2)}
    return out


def build_report(raw: dict, specs: dict, specs_source: str) -> dict:
    run, pos = raw["run"], raw["positions"]
    return {
        "task": "swap_cost",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "collector": "phase0.collectors.swap_deals",
            "collected_at_utc": run["collected_at_utc"],
            "broker": run["broker"],
            "endpoint": "/api/v1/deals + /api/v1/symbol_info (GET only)",
            "n_positions": len(pos),
            "n_nonzero_swap": run["n_nonzero_swap"],
            "span": run.get("span"),
            "largest_lot": max((p["lots"] for p in pos), default=0.0),
            "specs_source": specs_source,
        },
        "sign_convention": "MT5: negative is a charge, positive a credit",
        "triple_weekday": TRIPLE_WEEKDAY,
        "booked": booked(pos),
        "quoted": {"as_of": run["collected_at_utc"][:10],
                   "raw": run["symbol_info_swap"],
                   "usd_per_lot_night": quoted(run["symbol_info_swap"], specs)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raw", type=Path, help="swap_deals_raw_*.json")
    ap.add_argument("--specs", type=Path, required=True,
                    help="registry snapshot holding digits/tick_size/tick_value")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    raw = json.loads(args.raw.read_text())
    specs = json.loads(args.specs.read_text())["instruments"]
    report = build_report(raw, specs, args.specs.name)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
