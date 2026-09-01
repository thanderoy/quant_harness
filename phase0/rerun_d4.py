"""D4 re-run — effective breadth with AUDUSD and NZDUSD included.

The original D4 stamped its effective-N figures as **upper bounds** because
AUDUSD and NZDUSD were absent from the local CSVs. Both were later found to be
available from the broker (log seq=87), so the bound can be tested rather than
assumed.

The two arrivals are not equivalent, and the difference decides how much of the
caveat can actually be lifted:

  AUDUSD  54,958 H1 bars, 2017-10 -> 2026-08   (~9 years)
  NZDUSD  10,000 H1 bars, 2025-01 -> 2026-09   (~1.7 years)

NZDUSD is short because the terminal refused deeper history. A panel is
intersected across instruments, so including NZDUSD truncates *every* series to
~1.7 years. That is a different measurement, not a better one — a correlation
estimated over 1.7 years of one regime is not comparable to one over 5 years.
So this reports three variants and does not collapse them into a single
number.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WMPS = Path.home() / "Local" / "wine-mt5-python-setup"
DATA = WMPS / "research" / "data"
OUT = Path(__file__).resolve().parent

CORR_YEARS = 5
MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"]
METALS = ["XAUUSD", "XAGUSD"]

#: Sign-adjust so every series is "long the non-USD leg". Without this, USDJPY
#: and EURUSD look negatively correlated purely by quoting convention, which
#: would overstate diversification.
def sign_for(sym: str) -> float:
    return 1.0 if sym.endswith("USD") else -1.0


def load(sym: str) -> pd.DataFrame | None:
    p = DATA / f"{sym}_H1.csv"
    if not p.exists():
        return None
    df = pd.read_csv(
        p, sep=";", header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M",
    ).set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["close"]].astype(float)


def daily_returns(sym: str) -> pd.Series | None:
    df = load(sym)
    if df is None:
        return None
    d = df["close"].resample("1D").last().dropna()
    return np.log(d).diff().dropna() * sign_for(sym)


def effective_n(corr: pd.DataFrame, syms: list[str]) -> dict:
    sub = corr.loc[syms, syms].values
    k = len(syms)
    iu = np.triu_indices(k, 1)
    pair = sub[iu]
    rho_abs = float(np.mean(np.abs(pair)))
    rho_signed = float(np.mean(pair))
    return {
        "instruments": syms,
        "k": k,
        "avg_pairwise_abs_rho": rho_abs,
        "avg_pairwise_signed_rho": rho_signed,
        "effective_n_from_abs_rho": k / (1 + (k - 1) * rho_abs),
        "effective_n_from_signed_rho": k / (1 + (k - 1) * rho_signed),
    }


def variant(name: str, syms: list[str], rets: dict, cap_years: int | None) -> dict:
    avail = [s for s in syms if s in rets]
    panel = pd.DataFrame({s: rets[s] for s in avail}).dropna()
    if cap_years is not None:
        cutoff = panel.index[-1] - pd.DateOffset(years=cap_years)
        panel = panel.loc[panel.index >= cutoff]
    corr = panel.corr()
    out = {
        "variant": name,
        "window_start": str(panel.index[0].date()),
        "window_end": str(panel.index[-1].date()),
        "n_observations": int(len(panel)),
        "correlation_matrix": json.loads(corr.round(6).to_json()),
    }
    # Groups are derived from what is actually in the panel, not from a fixed
    # MAJORS list — otherwise adding an instrument leaves the figures
    # unchanged and the run looks like a null result when it simply never
    # included the new series.
    fx = [s for s in avail if s not in METALS]
    groups = {"fx_only": fx, "fx_plus_metals": avail}
    for g, members in groups.items():
        if len(members) >= 2:
            out[g] = effective_n(corr, members)
    return out


def breadth_ceiling(rho_bar: float, target: float = 4.0) -> dict:
    """The ceiling on effective N for a given average correlation.

    effective_N = k / (1 + (k-1) * rho_bar)

    As k grows this converges to 1 / rho_bar. That limit is the whole game: no
    number of additional instruments can push effective breadth past it. If the
    Phase 2b target exceeds 1 / rho_bar, the target is unreachable by expansion
    and can only be met by lowering rho_bar — that is, by adding instruments
    driven by something other than the dollar.
    """
    ceiling = 1.0 / rho_bar if rho_bar > 0 else float("inf")
    max_rho_for_target = 1.0 / target
    return {
        "avg_pairwise_abs_rho": rho_bar,
        "effective_n_ceiling_as_k_to_infinity": ceiling,
        "target": target,
        "target_reachable_by_adding_instruments": ceiling >= target,
        "max_rho_bar_that_admits_target": max_rho_for_target,
        "verdict": (
            f"With rho_bar = {rho_bar:.3f} the ceiling is {ceiling:.2f}. "
            f"A target of {target:.0f} requires rho_bar <= {max_rho_for_target:.3f}, "
            f"so it cannot be reached by adding correlated instruments at any k."
        ),
    }


def main() -> None:
    universe = MAJORS + ["AUDUSD", "NZDUSD"] + METALS
    rets, missing = {}, []
    for s in universe:
        r = daily_returns(s)
        if r is None:
            missing.append(s)
        else:
            rets[s] = r
            print(f"  {s:8} {len(r):6} daily obs  {r.index[0].date()} -> {r.index[-1].date()}")

    variants = [
        variant("original_no_aud_nzd", MAJORS + METALS, rets, CORR_YEARS),
        variant("plus_audusd", MAJORS + ["AUDUSD"] + METALS, rets, CORR_YEARS),
        variant("plus_aud_and_nzd_short_window", universe, rets, None),
    ]

    artifact = {
        "task": "D4_rerun",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "phase0/rerun_d4.py",
        "supersedes": "d4_correlation in phase0_universe_20260831.json",
        "reason": ("AUDUSD and NZDUSD were absent from local CSVs, so the "
                   "original effective-N was stamped an UPPER BOUND. Both are "
                   "available from the broker (log seq=87)."),
        "missing_instruments": missing,
        "data_provenance": "MT5 rates via mt5-api on ganymede, 2026-09-01",
        "note": ("NZDUSD history is only ~1.7 years; a panel is intersected, so "
                 "including it truncates every series. The third variant is "
                 "therefore a DIFFERENT measurement, not a better one, and the "
                 "variants are not collapsed into a single figure."),
        "variants": variants,
        "breadth_ceiling": {
            v["variant"]: {
                g: breadth_ceiling(v[g]["avg_pairwise_abs_rho"])
                for g in ("fx_only", "fx_plus_metals") if g in v
            }
            for v in variants
        },
    }
    p = OUT / "d4_rerun_20260901.json"
    p.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"\nwrote {p.name}\n")

    print(f"{'variant':32} {'window':24} {'n':>5}  {'grp':20} {'k':>2} {'avg|rho|':>9} {'effN':>6}")
    for v in variants:
        for g in ("fx_only", "fx_plus_metals"):
            if g in v:
                b = v[g]
                print(f"{v['variant']:32} {v['window_start']}..{v['window_end']} "
                      f"{v['n_observations']:5}  {g:20} {b['k']:2} "
                      f"{b['avg_pairwise_abs_rho']:9.3f} "
                      f"{b['effective_n_from_abs_rho']:6.2f}")

    print("\n=== breadth ceiling (k -> infinity) ===")
    for v in variants:
        for g in ("fx_only", "fx_plus_metals"):
            if g in v:
                c = breadth_ceiling(v[g]["avg_pairwise_abs_rho"])
                print(f"  {v['variant']:32} {g:16} ceiling={c['effective_n_ceiling_as_k_to_infinity']:5.2f}  "
                      f"target 4 reachable: {c['target_reachable_by_adding_instruments']}")


if __name__ == "__main__":
    main()
