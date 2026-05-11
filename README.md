# qhf — Quant Harness for Forex (Phase 1)

A pre-registered, multiple-testing-aware validation harness for trading-strategy
research. Built for the discipline that the agentic-AI report demanded:
**no strategy passes without a positive Deflated Sharpe Ratio probability,
a low Probability of Backtest Overfitting, and a small IS–OOS Sharpe gap.**

It is engine-agnostic: it scores a returns series (or a returns matrix from a
parameter sweep). VectorBT, backtesting.py, MT5 strategy tester, or your own
loop — anything that produces per-period returns plugs in.

## What's in Phase 1 (this delivery)

| Module | Purpose |
|---|---|
| `qhf.metrics.core` | Sharpe, Sortino, Calmar, max DD, profit factor, expectancy, CAGR, summary |
| `qhf.metrics.deflated` | PSR (Bailey & López de Prado 2012), DSR (BLDP 2014), expected-max-Sharpe under null |
| `qhf.metrics.pbo` | Probability of Backtest Overfitting via CSCV (Bailey, Borwein, BLDP, Zhu 2017) |
| `qhf.validation.walk_forward` | Rolling and expanding train/test split generators with optional purge |
| `qhf.reports.scorecard` | Pre-registered gate evaluator with research-vs-production thresholds |

## Quick start

```bash
pip install -r requirements.txt
python -m examples.score_a_strategy
```

Expected output: a noise sweep that **FAILS** the gates, an alpha-injected sweep
that **PASSES**, and a walk-forward split demonstration. If your output disagrees
with the README's calibration table, the math is broken — investigate before
trusting any real strategy result.

### Calibration (verified on this machine)

| Scenario | Best IS Sharpe | PBO | DSR prob | Gate |
|---|---:|---:|---:|---|
| 20 i.i.d. zero-mean strategies, 2000 obs | 0.78 | 0.37 | 0.65 | **FAIL** |
| 1 alpha (~17% ann.) hidden among 19 noisy | 2.14 | 0.00 | 1.00 | **PASS** |

## Default acceptance gates

```python
Thresholds(
    is_oos_gap_max     = 0.5,    # IS-OOS Sharpe gap
    pbo_max            = 0.5,    # Beats coin-flip overfitting
    dsr_prob_min       = 0.95,   # Significant after multiple testing
    max_dd_oos_max     = 0.30,   # Survivable OOS drawdown
    n_trades_oos_min   = 30,     # Statistical power
    profit_factor_oos_min = 1.20,
)
```

For live-capital deployment, use `Thresholds.production()` which tightens to
0.3 / 0.3 / 0.99 / 0.15 / 100 / 1.40 respectively.

## API at a glance

```python
import pandas as pd
from qhf.metrics import sharpe_ratio, summarize, dsr_from_trials, pbo
from qhf.validation import rolling_splits
from qhf.reports import Result, Thresholds, evaluate

# returns_matrix: T x N DataFrame, one column per parameter combination
pbo_result = pbo(returns_matrix, S=16, periods_per_year=252)
dsr_result = dsr_from_trials(returns_matrix, periods_per_year=252)

# Walk-forward
for train, test in rolling_splits(df, train_size="1460D", test_size="365D"):
    ...

# Score
report = evaluate(Result(
    name="HMA+Stoch 1H",
    is_sharpe=1.4, oos_sharpe=1.1,
    is_max_dd=0.18, oos_max_dd=0.22,
    n_trades_oos=160, profit_factor_oos=1.55,
    pbo=pbo_result["pbo"],
    dsr_probability=dsr_result["dsr_probability"],
))
print(report)
```

## Annualisation factors (forex relevant)

| Bar timeframe | `periods_per_year` |
|---|---:|
| Daily (forex 5d/wk) | 252 |
| H4 | 252 × 6 = 1512 |
| H1 | 252 × 24 = 6048 |
| M15 | 252 × 24 × 4 = 24192 |
| Trade-level returns | (estimate) trades_per_year |

For trade-level returns, use the actual trade count divided by years observed.

## "How honest must I be about num_trials?"

**Brutally.** `num_trials` is the total count of variants you've evaluated on
this dataset across your entire research program — every parameter sweep cell,
every discarded predecessor, every "I just want to try one more thing." If you
ran a 5×5×5 = 125 cell parameter sweep last week and a 3-variant sweep today,
`num_trials = 128`. Lying to the harness means lying to yourself. The whole
point of DSR is to defend against the fact that you've already eaten the
multiple-testing penalty whether or not you've counted.

`dsr_from_trials(...)` accepts `extra_trials=K` to add discarded prior work.

## What's coming in Phase 2

| Module | Purpose |
|---|---|
| `qhf.data.mt5_loader` | Pull XAUUSD bars from MetaTrader5 Python lib, cache to Parquet |
| `qhf.engines.vbt_runner` | VectorBT wrapper: parameterised strategy → T×N returns matrix |
| `qhf.engines.btpy_runner` | backtesting.py wrapper: realistic fills + Pepperstone cost model |
| `qhf.validation.stress` | Spread/cost stress (1.5×, 2× spread); ±20% parameter sensitivity |
| `qhf.reports.tearsheet` | HTML/PDF tearsheet generator |

The split is deliberate: Phase 1 is the engine-agnostic math; Phase 2 is the IO
layer that connects to your backtesting frameworks and Pepperstone's cost model.

## References (read these, not just cite)

- Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier." *J. Risk* 15(2).
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio." *J. Portfolio Management* 40(5).
- Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2017). "The Probability of Backtest Overfitting." *J. Computational Finance* 20(4).
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley. — esp. Ch. 7 (CV pitfalls), Ch. 11 (backtesting), Ch. 12 (statistics of backtesting).
- Lo, A. (2002). "The Statistics of Sharpe Ratios." *Financial Analysts Journal*.
- Mertens, E. (2002). "Variance of the IID estimator of the Sharpe ratio." Working paper.

## License

Internal research code. No warranty.
