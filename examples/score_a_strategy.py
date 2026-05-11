"""examples/score_a_strategy.py — calibration demo & usage example.

Run from repo root:

    python -m examples.score_a_strategy

Three scenarios:
    1. Pure-noise parameter sweep        (gates should FAIL)
    2. Sweep with one genuinely-positive  (gates should PASS, on the winner)
    3. Walk-forward split demonstration   (just shows the iterator)

If scenarios 1 and 2 don't behave as advertised, the math is broken.
This is the regression test you run before trusting the harness with
real strategy returns.
"""

import numpy as np
import pandas as pd

from qhf.metrics.core import sharpe_ratio, summarize
from qhf.metrics.deflated import dsr_from_trials
from qhf.metrics.pbo import pbo
from qhf.reports.scorecard import Result, Thresholds, evaluate
from qhf.validation.walk_forward import rolling_splits


PERIODS_PER_YEAR_DAILY = 252


def _noise(T=2000, N=20, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0.0, 0.01, size=(T, N)),
        columns=[f"s_{i:02d}" for i in range(N)],
    )


def _noise_with_alpha(T=2000, N=20, alpha_per=0.0012,
                      alpha_idx=5, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 0.01, size=(T, N))
    data[:, alpha_idx] += alpha_per
    return pd.DataFrame(data, columns=[f"s_{i:02d}" for i in range(N)])


def _fmt(x, digits=3):
    if isinstance(x, float):
        if not np.isfinite(x):
            return str(x)
        return f"{x:.{digits}f}"
    return str(x)


def demo_noise():
    print("=" * 72)
    print("DEMO 1: Pure-noise sweep (20 i.i.d. zero-mean strategies, 8y daily)")
    print("=" * 72)
    M = _noise(T=2000, N=20)
    pbo_res = pbo(M, S=16, periods_per_year=PERIODS_PER_YEAR_DAILY)
    dsr_res = dsr_from_trials(M, periods_per_year=PERIODS_PER_YEAR_DAILY)

    print(f"  PBO                : {_fmt(pbo_res['pbo'])} ({pbo_res['verdict']})")
    print(f"  Best winner column : {dsr_res['winner']}")
    print(f"  Best Sharpe (IS)   : {_fmt(dsr_res['sharpe_obs_annualised'], 2)}")
    print(f"  Expected max SR    : {_fmt(dsr_res['sr_benchmark_annualised'], 2)}")
    print(f"  Deflated value     : {_fmt(dsr_res['deflated_value_annualised'], 2)}")
    print(f"  DSR probability    : {_fmt(dsr_res['dsr_probability'])}")

    # Score the noise winner.
    winner = dsr_res["winner"]
    wr = M[winner]
    half = len(wr) // 2
    is_part, oos_part = wr.iloc[:half], wr.iloc[half:]
    full = summarize(wr, PERIODS_PER_YEAR_DAILY)
    res = Result(
        name=f"Noise winner ({winner})",
        is_sharpe=sharpe_ratio(is_part, PERIODS_PER_YEAR_DAILY),
        oos_sharpe=sharpe_ratio(oos_part, PERIODS_PER_YEAR_DAILY),
        is_max_dd=full["max_drawdown"],
        oos_max_dd=full["max_drawdown"],
        n_trades_oos=len(oos_part),
        profit_factor_oos=full["profit_factor"],
        pbo=pbo_res["pbo"],
        dsr_probability=dsr_res["dsr_probability"],
    )
    report = evaluate(res, Thresholds())
    print()
    print("  ---- Scorecard ----")
    print("  ", str(report).replace("\n", "\n  "))
    print()


def demo_alpha():
    print("=" * 72)
    print("DEMO 2: One genuine-alpha strategy hidden among 19 noisy ones")
    print("=" * 72)
    M = _noise_with_alpha(T=2000, N=20, alpha_per=0.0012, alpha_idx=5)
    pbo_res = pbo(M, S=16, periods_per_year=PERIODS_PER_YEAR_DAILY)
    dsr_res = dsr_from_trials(M, periods_per_year=PERIODS_PER_YEAR_DAILY)

    print(f"  PBO                : {_fmt(pbo_res['pbo'])} ({pbo_res['verdict']})")
    print(f"  Best winner column : {dsr_res['winner']} "
          f"(injected alpha at s_05)")
    print(f"  Best Sharpe (IS)   : {_fmt(dsr_res['sharpe_obs_annualised'], 2)}")
    print(f"  Expected max SR    : {_fmt(dsr_res['sr_benchmark_annualised'], 2)}")
    print(f"  Deflated value     : {_fmt(dsr_res['deflated_value_annualised'], 2)}")
    print(f"  DSR probability    : {_fmt(dsr_res['dsr_probability'])}")
    print()
    print("  Expectation: PBO ~ 0.0, DSR probability > 0.95")
    print("  (A real edge should beat the deflated-Sharpe gate.)")
    print()

    # Build a Result and run the gate evaluator on the winner.
    winner = dsr_res["winner"]
    winner_returns = M[winner]
    full = summarize(winner_returns, PERIODS_PER_YEAR_DAILY)

    # For the demo we use the same returns for IS and OOS Sharpe; in real
    # use IS comes from the parameter-selected period and OOS from a held-out
    # period. We're just exercising the scorecard plumbing.
    half = len(winner_returns) // 2
    is_part = winner_returns.iloc[:half]
    oos_part = winner_returns.iloc[half:]
    is_sr = sharpe_ratio(is_part, PERIODS_PER_YEAR_DAILY)
    oos_sr = sharpe_ratio(oos_part, PERIODS_PER_YEAR_DAILY)

    res = Result(
        name=f"Synthetic alpha winner ({winner})",
        is_sharpe=is_sr,
        oos_sharpe=oos_sr,
        is_max_dd=full["max_drawdown"],
        oos_max_dd=full["max_drawdown"],
        n_trades_oos=len(oos_part),  # one "trade" per period in this synthetic
        profit_factor_oos=full["profit_factor"],
        pbo=pbo_res["pbo"],
        dsr_probability=dsr_res["dsr_probability"],
    )
    report = evaluate(res, Thresholds())
    print("  ---- Scorecard ----")
    print("  ", str(report).replace("\n", "\n  "))
    print()


def demo_walk_forward():
    print("=" * 72)
    print("DEMO 3: Walk-forward split iterator (illustrative)")
    print("=" * 72)
    idx = pd.date_range("2010-01-01", "2025-12-31", freq="D")
    df = pd.DataFrame({"close": np.random.default_rng(0).normal(2000, 50, len(idx))},
                      index=idx)

    print("  Rolling: 4 years train / 1 year OOS, rolled annually:")
    for i, (train, test) in enumerate(rolling_splits(df, "1460D", "365D")):
        print(f"    Split {i+1}: train {train.index.min().date()} -> "
              f"{train.index.max().date()}  |  test {test.index.min().date()} -> "
              f"{test.index.max().date()}")
        if i >= 4:
            print("    ...")
            break
    print()


def main():
    demo_noise()
    demo_alpha()
    demo_walk_forward()


if __name__ == "__main__":
    main()
