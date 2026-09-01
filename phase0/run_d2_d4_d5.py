"""D2 / D4 / D5 — granularity, correlation and benchmark Sharpe.

Phase 0. Runs on locally available data only. Everything it produces is
stamped:

  PARTIAL_UNIVERSE  — AUDUSD and NZDUSD have no local history at all, so any
                      effective-N figure here is an UPPER BOUND, not an
                      estimate (spec D4).
  PROVISIONAL_SPECS — D1 is BLOCKED (no MT5 terminal), so contract specs below
                      are HAND_ENTERED standard values, not broker-confirmed.
                      Per the T1 provenance refusal rule, nothing derived from
                      them may satisfy an acceptance criterion or be logged as
                      a result.

Writes research artifact JSON next to this script.
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

ACCOUNT_EQUITY = 100.0
TARGET_RISK_PCT = 0.02
STOP_ATR_MULT = 1.5
ATR_PERIOD = 14
MEDIAN_ATR_MONTHS = 24
CORR_YEARS = 5

# --- HAND_ENTERED contract specs (D1 is BLOCKED) --------------------------
# Standard retail FX/metals values. NOT broker-confirmed.
SPECS = {
    "EURUSD": dict(contract_size=100_000, min_lot=0.01, quote_ccy="USD", base_ccy="EUR"),
    "GBPUSD": dict(contract_size=100_000, min_lot=0.01, quote_ccy="USD", base_ccy="GBP"),
    "USDJPY": dict(contract_size=100_000, min_lot=0.01, quote_ccy="JPY", base_ccy="USD"),
    "USDCHF": dict(contract_size=100_000, min_lot=0.01, quote_ccy="CHF", base_ccy="USD"),
    "USDCAD": dict(contract_size=100_000, min_lot=0.01, quote_ccy="CAD", base_ccy="USD"),
    "XAUUSD": dict(contract_size=100,     min_lot=0.01, quote_ccy="USD", base_ccy="XAU"),
    "XAGUSD": dict(contract_size=5_000,   min_lot=0.01, quote_ccy="USD", base_ccy="XAG"),
}
MISSING = ["AUDUSD", "NZDUSD"]

# Sign adjustment for D4: +1 where the quote is USD (return = base vs USD),
# -1 where USD is the base, so every series measures "foreign vs USD".
SIGN = {s: (1.0 if v["quote_ccy"] == "USD" else -1.0) for s, v in SPECS.items()}


def load(sym: str, tf: str = "H1") -> pd.DataFrame | None:
    p = DATA / f"{sym}_{tf}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(
        p, sep=";", header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M",
    ).set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].astype(float)


def atr_wilder(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Wilder ATR, vectorised. Matches the WMPS recursive implementation to
    float tolerance; used here for speed on 80k-bar series."""
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def to_h4(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h").agg({"open": "first", "high": "max",
                                  "low": "min", "close": "last"}).dropna()


def min_position_risk_usd(sym: str, stop_price_units: float,
                          quote_rate: float) -> float:
    """Account-currency (USD) risk of one min_lot position.

    units      = min_lot * contract_size          (base-currency units)
    risk_quote = units * stop_distance            (quote currency)
    risk_usd   = risk_quote converted to USD
    """
    spec = SPECS[sym]
    units = spec["min_lot"] * spec["contract_size"]
    risk_quote = units * stop_price_units
    if spec["quote_ccy"] == "USD":
        return risk_quote
    # Quote is JPY/CHF/CAD and the pair is USDXXX, so its own rate converts.
    return risk_quote / quote_rate


def run_d2(frames: dict) -> dict:
    rows = []
    for sym, h1 in frames.items():
        cutoff = h1.index[-1] - pd.DateOffset(months=MEDIAN_ATR_MONTHS)
        for tf, df in (("H1", h1), ("H4", to_h4(h1))):
            a = atr_wilder(df)
            recent = a.loc[a.index >= cutoff].dropna()
            med_atr = float(recent.median())
            stop = STOP_ATR_MULT * med_atr
            rate = float(df["close"].loc[df.index >= cutoff].median())
            risk = min_position_risk_usd(sym, stop, rate)
            pct = risk / ACCOUNT_EQUITY
            rows.append({
                "symbol": sym, "timeframe": tf,
                "median_atr_24m": med_atr,
                "stop_distance_price": stop,
                "median_price": rate,
                "min_lot": SPECS[sym]["min_lot"],
                "contract_size": SPECS[sym]["contract_size"],
                "min_position_risk_usd": risk,
                "min_position_risk_pct_of_100": pct,
                "tradable_at_capital": bool(pct <= TARGET_RISK_PCT),
            })
    return {
        "provenance": "PROVISIONAL_SPECS",
        "universe_status": "PARTIAL_UNIVERSE",
        "missing_instruments": MISSING,
        "account_equity_usd": ACCOUNT_EQUITY,
        "target_risk_pct": TARGET_RISK_PCT,
        "stop_atr_multiplier": STOP_ATR_MULT,
        "atr_period": ATR_PERIOD,
        "median_window_months": MEDIAN_ATR_MONTHS,
        "rows": rows,
    }


def run_d4(frames: dict) -> dict:
    daily = {}
    for sym, h1 in frames.items():
        d = h1["close"].resample("1D").last().dropna()
        r = np.log(d).diff().dropna() * SIGN[sym]
        daily[sym] = r
    panel = pd.DataFrame(daily).dropna()
    cutoff = panel.index[-1] - pd.DateOffset(years=CORR_YEARS)
    panel = panel.loc[panel.index >= cutoff]
    corr = panel.corr()

    def eff_n(syms: list[str]) -> dict:
        sub = corr.loc[syms, syms].values
        k = len(syms)
        iu = np.triu_indices(k, 1)
        pair = sub[iu]
        rho_abs = float(np.mean(np.abs(pair)))
        rho_signed = float(np.mean(pair))
        return {
            "instruments": syms, "k": k,
            "avg_pairwise_abs_rho": rho_abs,
            "avg_pairwise_signed_rho": rho_signed,
            "effective_n_from_abs_rho": k / (1 + (k - 1) * rho_abs),
            "effective_n_from_signed_rho": k / (1 + (k - 1) * rho_signed),
        }

    majors = [s for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"]
              if s in corr.columns]
    metals = [s for s in ["XAUUSD", "XAGUSD"] if s in corr.columns]
    return {
        "universe_status": "PARTIAL_UNIVERSE",
        "missing_instruments": MISSING,
        "note": ("AUDUSD and NZDUSD absent. They correlate strongly with each "
                 "other and with the commodity complex, so every effective-N "
                 "below is an UPPER BOUND on true breadth."),
        "window_years": CORR_YEARS,
        "window_start": str(panel.index[0].date()),
        "window_end": str(panel.index[-1].date()),
        "n_observations": int(len(panel)),
        "sign_adjustment": SIGN,
        "correlation_matrix": json.loads(corr.round(6).to_json()),
        "majors_available_only": eff_n(majors),
        "majors_plus_metals": eff_n(majors + metals),
    }


def run_d5(frames: dict) -> dict:
    rows = []
    per_inst_rets = {}
    for sym, h1 in frames.items():
        d = h1["close"].resample("1D").last().dropna()
        r = np.log(d).diff().dropna()
        per_inst_rets[sym] = r
        ann = float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if r.std(ddof=1) > 0 else float("nan")
        rows.append({
            "symbol": sym,
            "start": str(r.index[0].date()), "end": str(r.index[-1].date()),
            "n_days": int(len(r)),
            "mean_daily_log_return": float(r.mean()),
            "daily_vol": float(r.std(ddof=1)),
            "buy_and_hold_sharpe_annualised": ann,
        })
    panel = pd.DataFrame(per_inst_rets).dropna()
    inv_vol = 1.0 / panel.std(ddof=1)
    w = inv_vol / inv_vol.sum()
    port = (panel * w).sum(axis=1)
    port_sr = float(port.mean() / port.std(ddof=1) * np.sqrt(252))
    return {
        "universe_status": "PARTIAL_UNIVERSE",
        "missing_instruments": MISSING,
        "rf_rate": 0.0,
        "annualisation_factor": 252,
        "note": ("SR* for DSR. Long-only buy-and-hold, zero risk-free rate. "
                 "Near-zero for FX majors is the expected and desirable result; "
                 "the metals values are not, which is why gold results must be "
                 "re-evaluated against a non-zero SR* (spec T8)."),
        "per_instrument": rows,
        "equal_risk_weighted_panel": {
            "weights": {k: float(v) for k, v in w.items()},
            "n_days": int(len(port)),
            "sharpe_annualised": port_sr,
        },
    }


def main() -> None:
    frames = {}
    for sym in SPECS:
        df = load(sym)
        if df is None:
            print(f"  MISSING data: {sym}")
            continue
        frames[sym] = df
        print(f"  loaded {sym}: {len(df)} H1 bars  {df.index[0].date()} -> {df.index[-1].date()}")

    artifact = {
        "task": "phase0_universe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "phase0/run_d2_d4_d5.py",
        "stamps": ["PARTIAL_UNIVERSE", "PROVISIONAL_SPECS"],
        "d1_contract_specs": {
            "status": "BLOCKED",
            "dependency": "MT5 terminal unavailable (mt5 / mt5-test containers down)",
            "provenance": "HAND_ENTERED",
            "specs_used": SPECS,
            "note": ("Standard retail values, NOT broker-confirmed. Registry.load() "
                     "must refuse these without allow_provisional=True (T1)."),
        },
        "d2_granularity": run_d2(frames),
        "d3_spread_cost": {
            "status": "BLOCKED",
            "d3a_forward_collector": "not started — requires live MT5",
            "d3b_historical": "not attempted — requires copy_ticks_range",
            "note": ("Local CSVs are Date;Open;High;Low;Close;Volume with no "
                     "spread column, so no spread statistic is derivable offline."),
        },
        "d4_correlation": run_d4(frames),
        "d5_benchmark_sharpe": run_d5(frames),
    }
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = OUT / f"phase0_universe_{date}.json"
    path.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"\nwrote {path}")

    d2 = artifact["d2_granularity"]["rows"]
    print("\n=== D2 granularity at $100, 2% budget, 1.5xATR stop ===")
    print(f"{'symbol':8} {'tf':4} {'med ATR':>10} {'risk $':>9} {'risk %':>8}  tradable")
    for r in d2:
        print(f"{r['symbol']:8} {r['timeframe']:4} {r['median_atr_24m']:10.5f} "
              f"{r['min_position_risk_usd']:9.2f} {r['min_position_risk_pct_of_100']:7.2%}  "
              f"{'YES' if r['tradable_at_capital'] else 'no'}")

    print("\n=== D4 effective breadth (UPPER BOUND) ===")
    for k in ("majors_available_only", "majors_plus_metals"):
        b = artifact["d4_correlation"][k]
        print(f"{k:24} k={b['k']}  avg|rho|={b['avg_pairwise_abs_rho']:.3f}  "
              f"eff_N={b['effective_n_from_abs_rho']:.2f}")

    print("\n=== D5 buy-and-hold Sharpe (SR*) ===")
    for r in artifact["d5_benchmark_sharpe"]["per_instrument"]:
        print(f"{r['symbol']:8} {r['buy_and_hold_sharpe_annualised']:+.3f}   "
              f"({r['start']} -> {r['end']}, {r['n_days']}d)")
    p = artifact["d5_benchmark_sharpe"]["equal_risk_weighted_panel"]
    print(f"{'PANEL':8} {p['sharpe_annualised']:+.3f}   (equal-risk-weighted)")


if __name__ == "__main__":
    main()
