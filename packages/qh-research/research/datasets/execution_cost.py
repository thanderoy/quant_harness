"""research.datasets.execution_cost — execution cost measured from live fills.

Reduces the per-fill dump written by ``phase0.collectors.execution_fills`` to
per-symbol, per-side aggregates. The dump stays out of the repo; only what this
module returns is committed.

Two estimators, kept apart because they answer different questions.

``quote`` — fill against the tick quote standing before it
    ``pre`` is the last bid/ask in a second strictly before the fill's. For a
    buy the touch is the ask, for a sell the bid. Two numbers per fill:

    * ``slip`` = side * (fill - touch). Slip past the touch, in the
      convention ``SlipModel`` charges on top of a half spread.
    * ``vs_mid`` = side * (fill - mid). Total execution cost per side: half
      the spread at the fill plus slip.

    It is relative to the quote at *fill* time, not to the price the request
    saw, which the deal does not carry. Drift between request and fill inside
    the one-second resolution of ``/api/v1/ticks`` is in it; drift before that
    is not.

``bar`` — fill against the M5 bar containing it
    The method that needs no ticks. MT5 bars are built from the **bid**, so a
    buy (filled at the ask) carries the full spread against a bar and a sell
    carries none. The bar estimate therefore never separates spread from slip
    and is reported per side, with that asymmetry stated, as a cross-check on
    the quote estimator — not as the figure the model uses. It also carries
    the intrabar drift between the reference and the fill.

Sign convention everywhere: positive is adverse. ``side`` is +1 for a buy and
-1 for a sell, so a buy that paid up and a sell that was paid down are both
positive and a favourable fill is negative. Nothing is clipped at zero —
clipping turns noise into cost.

Entry-conditional (R7): the headline is the ``IN`` leg only — the cost when an
entry actually fires. Exits are summarised separately because stop and limit
fills are a different mechanism.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from research import admission
from research import data_manifest as dm

__all__ = [
    "SIDE_SIGN",
    "alignment_scan",
    "bar_costs",
    "quote_costs",
    "summarise",
    "build_report",
]

SIDE_SIGN = {"BUY": 1.0, "SELL": -1.0}

#: Quantiles reported for every distribution.
QUANTILES = (0.5, 0.75, 0.9)

#: Clock offsets, in hours, tried by the bar alignment scan. The server is
#: EET (UTC+2/+3), so a deal time mistakenly in UTC would show up at +2/+3.
ALIGNMENT_OFFSETS_H = (-3, -2, -1, 0, 1, 2, 3)

BAR_MINUTES = 5


def _signed(side: str, fill: float, ref: float) -> float:
    return SIDE_SIGN[side] * (fill - ref)


def _quote_row(side: str, fill: float, q: Optional[dict]) -> tuple[float, float, float]:
    """(spread, slip vs touch, cost vs mid) against one quote; NaN if none."""
    if not q:
        return math.nan, math.nan, math.nan
    bid, ask = float(q["bid"]), float(q["ask"])
    touch = ask if side == "BUY" else bid
    return (ask - bid, _signed(side, fill, touch),
            _signed(side, fill, (bid + ask) / 2.0))


def quote_costs(fills: Iterable[dict]) -> pd.DataFrame:
    """One row per fill that has a ``pre`` quote, costs in price units.

    ``slip``/``vs_mid`` are against ``pre``, the quote unambiguously before
    the fill. ``slip_same``/``vs_mid_same`` are against the last quote in the
    fill's own second, which may postdate the fill; NaN when that second has
    no tick. The two bracket the drift inside the one-second resolution.
    """
    rows = []
    for f in fills:
        quotes = f.get("quotes") or {}
        if not quotes.get("pre"):
            continue
        side, fill = f["side"], float(f["price"])
        spread, slip, vs_mid = _quote_row(side, fill, quotes["pre"])
        _, slip_same, vs_mid_same = _quote_row(side, fill, quotes.get("same_last"))
        rows.append({
            "symbol": f["symbol"], "side": side, "entry": f["entry"],
            "reason": f["reason"], "time_msc": int(f["time_msc"]),
            "spread": spread, "slip": slip, "vs_mid": vs_mid,
            "slip_same": slip_same, "vs_mid_same": vs_mid_same,
            "staleness_s": f["time_msc"] // 1000 - int(quotes["pre"]["t"]),
        })
    return pd.DataFrame(rows)


def _bar_index(t_msc: int, offset_h: float = 0.0) -> pd.Timestamp:
    ts = pd.Timestamp(t_msc, unit="ms", tz="UTC") + pd.Timedelta(hours=offset_h)
    return ts.floor(f"{BAR_MINUTES}min")


def bar_costs(fills: Iterable[dict], bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Fill against its M5 bar, for fills whose bar exists in ``bars``.

    ``range_pos`` is where the fill sits in the bar's range, oriented so that
    1.0 is the worst price for its side (the high for a buy, the low for a
    sell). It can leave [0, 1]: a buy fills at the ask, above the bid bar.
    """
    rows = []
    for f in fills:
        df = bars.get(f["symbol"])
        if df is None:
            continue
        key = _bar_index(f["time_msc"])
        if key not in df.index:
            continue
        b = df.loc[key]
        fill, side = float(f["price"]), f["side"]
        rng = b.high - b.low
        if side == "BUY":
            pos = (fill - b.low) / rng if rng > 0 else math.nan
        else:
            pos = (b.high - fill) / rng if rng > 0 else math.nan
        rows.append({
            "symbol": f["symbol"], "side": side, "entry": f["entry"],
            "reason": f["reason"],
            "vs_open": _signed(side, fill, b.open),
            "vs_close": _signed(side, fill, b.close),
            "vs_mid": _signed(side, fill, (b.high + b.low) / 2.0),
            "range_pos": pos,
        })
    return pd.DataFrame(rows)


def alignment_scan(fills: list[dict], bars: dict[str, pd.DataFrame],
                   spreads: Optional[dict[str, float]] = None,
                   offsets_h: Iterable[float] = ALIGNMENT_OFFSETS_H) -> dict:
    """Share of fills inside their bar's range at each clock offset.

    A bid bar contains a sell fill outright; a buy fill sits up to one spread
    above it, so the high is widened by ``spreads[symbol]`` (a generous upper
    spread) for buys. With the right clock the share is near one; a wrong one
    puts the fill in a bar hours away and the share collapses.
    """
    spreads = spreads or {}
    out = {}
    for off in offsets_h:
        hit = n = 0
        for f in fills:
            df = bars.get(f["symbol"])
            if df is None:
                continue
            key = _bar_index(f["time_msc"], off)
            if key not in df.index:
                continue
            b = df.loc[key]
            widen = spreads.get(f["symbol"], 0.0) if f["side"] == "BUY" else 0.0
            n += 1
            hit += int(b.low <= float(f["price"]) <= b.high + widen)
        out[str(off)] = {"n": n, "inside": hit,
                         "share": round(hit / n, 4) if n else None}
    return out


def _dist(x: pd.Series, tick: float) -> dict:
    x = x.dropna().astype(float)
    if x.empty:
        return {"n": 0}
    qs = x.quantile(list(QUANTILES))
    price = {"mean": float(x.mean()), **{f"p{int(q * 100)}": float(qs[q])
                                         for q in QUANTILES}}
    return {
        "n": int(len(x)),
        "price": {k: round(v, 8) for k, v in price.items()},
        "ticks": {k: round(v / tick, 3) for k, v in price.items()},
        "share_adverse": round(float((x > 0).mean()), 4),
        "share_zero": round(float((x.abs() < tick / 2).mean()), 4),
    }


def summarise(df: pd.DataFrame, column: str,
              tick_size: dict[str, float]) -> dict:
    """Per symbol, per side and per symbol overall, for one cost column."""
    out: dict = {}
    if df.empty:
        return out
    for sym, g in df.groupby("symbol"):
        tick = tick_size[sym]
        rec = {"ALL": _dist(g[column], tick)}
        for side, gs in g.groupby("side"):
            rec[side] = _dist(gs[column], tick)
        out[sym] = rec
    return out


def load_bars(symbols: Iterable[str], bar_dir: Path,
              timeframe: str = "M5") -> tuple[dict[str, pd.DataFrame], dict]:
    """Admitted bars only. A refused or missing file contributes nothing."""
    bars, verdicts = {}, {}
    for sym in symbols:
        path = Path(bar_dir) / f"{sym}_{timeframe}.csv"
        if not path.exists():
            verdicts[sym] = {"verdict": "MISSING"}
            continue
        df = dm.load_ohlcv(path)
        a = admission.admit_frame(sym, timeframe, df)
        verdicts[sym] = {"verdict": a.verdict, "admit_from": a.admit_from,
                         "first_bar": str(df.index[0]),
                         "last_bar": str(df.index[-1]), "reasons": a.reasons}
        if a.verdict != admission.REFUSE:
            bars[sym] = df[df.index >= pd.Timestamp(a.admit_from)]
    return bars, verdicts


def _share_at_touch(q: pd.DataFrame, column: str,
                    tick_size: dict[str, float]) -> Optional[float]:
    """Share of fills within half a tick of the touch, among those measured."""
    if q.empty:
        return None
    x = q[column]
    ok = x.notna()
    if not ok.any():
        return None
    half = q.loc[ok, "symbol"].map(tick_size) / 2
    return float((x[ok].abs() < half).mean())


def _counts(fills: list[dict], key: str) -> dict:
    return {str(k): int(v) for k, v in
            pd.Series([f[key] for f in fills]).value_counts().sort_index().items()
            } if fills else {}


def build_report(raw: dict, bars: dict[str, pd.DataFrame],
                 bar_verdicts: dict) -> dict:
    """The committed aggregate. No per-fill row survives into it."""
    run, fills = raw["run"], raw["fills"]
    tick_size = {s: float(v["tick_size"]) for s, v in run["tick_size"].items()}
    entries = [f for f in fills if f["entry"] == "IN"]
    exits = [f for f in fills if f["entry"] != "IN"]

    q_in, q_out = quote_costs(entries), quote_costs(exits)
    b_in = bar_costs(entries, bars)

    # Generous spread for the alignment widening: the p99 quoted spread at
    # the fills themselves.
    q_all = quote_costs(fills)
    p99 = (q_all.groupby("symbol")["spread"].quantile(0.99).to_dict()
           if not q_all.empty else {})

    exact_touch = _share_at_touch(q_in, "slip", tick_size)
    exact_same = _share_at_touch(q_in, "slip_same", tick_size)
    return {
        "task": "execution_cost",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "collector": "phase0.collectors.execution_fills",
            "collected_at_utc": run["collected_at_utc"],
            "broker": run["broker"],
            "endpoint": "/api/v1/deals + /api/v1/ticks (GET only)",
            "n_trade_deals": len(fills),
            "n_entries": len(entries),
            "n_exits": len(exits),
            "span": run.get("span"),
            "symbols": sorted(tick_size),
            "tick_size": tick_size,
            "largest_lot": max(float(f["volume"]) for f in fills),
            "entries_by_reason": _counts(entries, "reason"),
            "exits_by_reason": _counts(exits, "reason"),
        },
        "sign_convention": "positive = adverse; side +1 buy, -1 sell",
        "clock_alignment": {
            "assumption": ("deal time_msc and tick times are the same MT5 "
                           "server-clock epoch; compared with no offset"),
            "entry_fills_exactly_at_pre_touch": (
                round(exact_touch, 4) if exact_touch is not None else None),
            "entry_fills_exactly_at_same_second_touch": (
                round(exact_same, 4) if exact_same is not None else None),
            "pre_quote_staleness_s": _dist(q_in["staleness_s"], 1.0)
            if not q_in.empty else None,
            "m5_bar_containment_by_offset_h": alignment_scan(fills, bars, p99),
        },
        "quote_method": {
            "description": ("fill vs the last tick quote in a second strictly "
                            "before the fill (tick times are 1 s resolution)"),
            "entries": {
                "slip_vs_touch": summarise(q_in, "slip", tick_size),
                "cost_vs_mid_per_side": summarise(q_in, "vs_mid", tick_size),
                "slip_vs_touch_same_second": summarise(q_in, "slip_same", tick_size),
                "cost_vs_mid_same_second": summarise(q_in, "vs_mid_same", tick_size),
                "spread_at_fill": summarise(q_in, "spread", tick_size),
                "slip_vs_touch_by_reason": {
                    r: summarise(g, "slip", tick_size)
                    for r, g in q_in.groupby("reason")} if not q_in.empty else {},
            },
            "exits": {
                "slip_vs_touch": summarise(q_out, "slip", tick_size),
                "cost_vs_mid_per_side": summarise(q_out, "vs_mid", tick_size),
            },
        },
        "bar_method": {
            "description": ("fill vs the admitted M5 bid bar containing it; a "
                            "buy carries the full spread against a bid bar, a "
                            "sell none; spread and slip not separable"),
            "bars": bar_verdicts,
            "n_entries_with_bar": int(len(b_in)),
            "entries": {
                "vs_open": summarise(b_in, "vs_open", tick_size),
                "vs_mid": summarise(b_in, "vs_mid", tick_size),
                "range_pos_worst_is_1": {
                    s: {k: round(float(v), 4) for k, v in
                        g["range_pos"].describe(percentiles=list(QUANTILES))
                        .drop(["count", "std"]).items()}
                    for s, g in b_in.groupby("symbol")} if not b_in.empty else {},
            },
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raw", type=Path, help="execution_fills_raw_*.json")
    ap.add_argument("--bar-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    raw = json.loads(args.raw.read_text())
    bars, verdicts = load_bars(raw["run"]["tick_size"], args.bar_dir)
    report = build_report(raw, bars, verdicts)
    args.out.write_text(json.dumps(report, indent=2, default=_np_default) + "\n")
    print(f"wrote {args.out}")
    return 0


def _np_default(o: object) -> object:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    raise SystemExit(main())
