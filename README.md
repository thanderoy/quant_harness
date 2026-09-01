# qhf — Quant Harness for Forex

A pre-registered, multiple-testing-aware validation harness for trading-strategy
research. Built to enforce the discipline that prevents the most common retail
quant failure: **strategies that look great in-sample and bleed in production.**

It is engine-agnostic. Anything that produces a per-period returns series — VectorBT,
backtesting.py, MT5 Strategy Tester output, or a hand-rolled Python loop — plugs
into the gates.

---

## What this enforces

Every strategy must clear six gates before it earns "validated" status:

| Gate | Default | What it catches |
|---|---|---|
| IS-OOS Sharpe gap | < 0.5 | In-sample overfit |
| Probability of Backtest Overfitting (PBO) | < 0.5 | Selecting on IS rank doesn't predict OOS rank |
| Deflated Sharpe Ratio probability (DSR) | > 0.95 | Sharpe not significant after multiple-testing penalty |
| OOS max drawdown | < 30% (research) / 20% (production) | Survivability |
| OOS trade count | ≥ 30 | Statistical power |
| OOS profit factor | ≥ 1.20 | Genuine edge over costs |

These are pre-registered: thresholds defined in code, **before** inspecting any
backtest result. That's the same discipline behind clinical-trial pre-registration —
prevents you from rationalising a fail into a pass after the fact.

For live capital, switch to `Thresholds.production()` which tightens to:
gap < 0.3, PBO < 0.3, DSR > 0.99, OOS DD < 15%, trades ≥ 100, PF ≥ 1.40.

---

## What's in the package

```
qhf/
├── metrics/
│   ├── core.py          # Sharpe, Sortino, Calmar, max DD, profit factor, expectancy
│   ├── deflated.py      # PSR & DSR (Bailey & López de Prado 2012, 2014)
│   └── pbo.py           # Probability of Backtest Overfitting (BLDPZ 2017)
├── validation/
│   └── walk_forward.py  # Rolling/expanding splits with exclude_ranges + reporting
├── reports/
│   └── scorecard.py     # Pre-registered gate evaluator
├── data/
│   ├── csv_loader.py    # MT5/generic CSV loader with auto-sniff & gap detection
│   └── cost_model.py    # Pepperstone XAUUSD Razor cost model
└── engines/             # (Phase 2b — coming next)
    └── (empty)

examples/
├── score_a_strategy.py  # Calibration demo: noise FAILs gates, alpha PASSes
├── load_and_cost.py     # Loader + cost model end-to-end demo
└── gap_report.py        # Diagnostic for data gaps in CSV files

tests/                   # 53 tests, all passing
```

---

## Quick start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify on your machine
python -m unittest discover tests -v
# expected: Ran 53 tests in [time]s — OK

# Calibration check (synthetic data)
python -m examples.score_a_strategy
# expected: Demo 1 (noise) FAILs gates; Demo 2 (alpha) PASSes
```

If 53/53 tests pass and the calibration demo behaves as described, the harness
is trustworthy on your machine.

---

## Calibration (verified)

| Scenario | Best IS Sharpe | PBO | DSR prob | Gate verdict |
|---|---:|---:|---:|---|
| 20 i.i.d. zero-mean strategies, 2000 obs | 0.78 | 0.37 | 0.65 | **FAIL** ✓ |
| 1 alpha (~17% ann.) hidden among 19 noisy | 2.14 | 0.00 | 1.00 | **PASS** ✓ |

Pure noise must FAIL; genuine alpha must PASS. If your output disagrees, the math
is wrong — investigate before trusting any real strategy result.

---

## Working with real data

### CSV loading

The loader auto-sniffs delimiter (tab/comma/semicolon), normalises headers
(`Date`/`time`/`timestamp` etc.), parses MT5 native dates (`YYYY.MM.DD HH:MM`),
and reports diagnostics including timeframe inference, gap detection, and OHLC
sanity.

```python
from qhf.data import load_bars

result = load_bars("data/raw/XAUUSD_H1.csv", expected_timeframe="H1")
print(result.summary_str())
# rows, timeframe, span_years, gaps, warnings...

df = result.df  # DatetimeIndex'd OHLCV DataFrame
```

### Cost model

```python
from qhf.data import PepperstoneXAUUSDCostModel
from datetime import datetime

cost = PepperstoneXAUUSDCostModel()
# Defaults: $0.22/oz spread, $7 RT/lot commission (MT5 Razor), placeholder swaps
breakdown = cost.trade_cost(
    lots=0.10, direction="BUY",
    entry_dt=datetime(2024, 5, 6, 12, 0),
    exit_dt=datetime(2024, 5, 11, 12, 0),  # 5 nights, includes Wed-triple
)
# breakdown.spread_usd, .commission_usd, .swap_usd, .total_usd
```

**Override swap rates with current values from MT5 Symbol Specifications**
for production accuracy. Pepperstone updates these weekly.

### Walk-forward splits with exclusion

```python
from qhf.validation import (
    rolling_splits, rolling_splits_with_report, SplitReport
)

# Plain
for train, test in rolling_splits(df, "1460D", "365D"):  # 4y / 1y rolled annually
    ...

# With exclusion of broker-history gap and reporting
report = SplitReport()
folds = list(rolling_splits_with_report(
    df, "1460D", "365D",
    exclude_ranges=[("2025-09-12", "2025-10-15")],
    report=report,
))
print(report.summary_str())
# SplitReport: 16 folds used / 1 excluded / 17 total
#   excluded fold #16: ... (overlaps test window with 2025-09-12..2025-10-15)
```

### Scoring against the gates

```python
from qhf.metrics import dsr_from_trials, pbo
from qhf.reports import Result, Thresholds, evaluate

# returns_matrix: T x N DataFrame of per-period returns from a parameter sweep
pbo_result = pbo(returns_matrix, S=16, periods_per_year=252)
dsr_result = dsr_from_trials(returns_matrix, periods_per_year=252)

result = Result(
    name="HMA+Stoch 1H v1.1",
    is_sharpe=1.4, oos_sharpe=1.1,
    is_max_dd=0.18, oos_max_dd=0.22,
    n_trades_oos=160, profit_factor_oos=1.55,
    pbo=pbo_result["pbo"],
    dsr_probability=dsr_result["dsr_probability"],
)
report = evaluate(result, Thresholds())
print(report)
# [PASS] HMA+Stoch 1H v1.1
# or
# [FAIL] HMA+Stoch 1H v1.1
#   - DSR probability = 0.83 < threshold 0.95 (...)
```

---

## Annualisation factors (forex relevant)

| Bar timeframe | `periods_per_year` |
|---|---:|
| Daily (forex 5d/wk) | 252 |
| H4 | 1,512 (252 × 6) |
| H1 | 6,048 (252 × 24) |
| M15 | 24,192 (252 × 24 × 4) |
| M5 | 72,576 (252 × 24 × 12) |
| Trade-level returns | (estimate) trades_per_year |

For trade-level returns, use the actual trade count divided by years observed.

---

## On honesty about `num_trials`

`num_trials` in `dsr()` is the total count of variants evaluated on this dataset
across your entire research program — every parameter sweep cell, every discarded
predecessor, every "I just want to try one more thing." If you ran a 5×5×5 = 125
cell parameter sweep last week and a 3-variant sweep today, `num_trials = 128`.

Lying to the harness means lying to yourself. The whole point of DSR is to defend
against the fact that you've already eaten the multiple-testing penalty whether
or not you've counted. `dsr_from_trials(...)` accepts `extra_trials=K` to add
discarded prior work.

---

## Pepperstone XAUUSD Razor cost reference

Cost model defaults are documented Pepperstone values as of 2025–2026:

| Field | Value | Source |
|---|---|---|
| Contract size | 100 oz / lot | Pepperstone docs |
| Min lot | 0.01 | Pepperstone docs |
| Lot step | 0.01 | Pepperstone docs |
| Commission (MT5 Razor) | $7 round-turn / lot ($0.07 per 0.01 lot) | Pepperstone docs |
| Spread (typical) | ~$0.22 / oz | User-observed; Pepperstone-published range $0.05–$0.30 |
| Triple-swap day | Wednesday rollover | Pepperstone docs |
| Server rollover | 5pm New York / 23:59 server time | Pepperstone docs |
| Swap rates | floating, weekly-updated | Override from MT5 Symbol Specifications |
| Stops level | floor at $0.10/oz (assumed) | Verify in MT5 |

Practical implication: a 0.01 lot intraday round-trip costs roughly $0.29. With
2% risk on a $100 account = $2 per trade, costs are ~14% of risk. Strategy must
overcome this drag before any losses to be profitable.

---

## Architecture principle

The harness scores returns. It does not run strategies. The reason for the split
is auditability:

```
[Strategy code]  →  per-period returns series  →  [qhf]  →  pass/fail report
                          (engine-agnostic)
```

Whatever produces the returns — VectorBT for breadth (parameter sweeps),
backtesting.py for depth (path-dependent), MT5 Strategy Tester for ground
truth — is interchangeable. Only the returns matter to the gates.

---

## What's coming

| Phase | Module | Status |
|---|---|---|
| 1 | metrics, walk_forward, scorecard | ✅ done |
| 2a | csv_loader, cost_model, exclude_ranges, gap_report | ✅ done |
| 2b | engines.btpy_runner (backtesting.py wrapper, path-dependent) | ⏭ next |
| 2c | validation.stress (spread shock + parameter sensitivity) | ⏭ after 2b |
| 3 | engines.vbt_runner (VectorBT for parameter sweeps) | ⏭ later |
| 3 | reports.tearsheet (HTML/PDF strategy report) | ⏭ later |

---

## References (read these, not just cite)

- Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier." *J. Risk* 15(2).
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio." *J. Portfolio Management* 40(5).
- Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2017). "The Probability of Backtest Overfitting." *J. Computational Finance* 20(4).
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley. — esp. Ch. 7 (CV pitfalls), Ch. 11 (backtesting), Ch. 12 (statistics of backtesting).
- Lo, A. (2002). "The Statistics of Sharpe Ratios." *Financial Analysts Journal*.
- Mertens, E. (2002). "Variance of the IID estimator of the Sharpe ratio." Working paper.
- Harvey & Liu (2015). "Backtesting." *J. Portfolio Management* — multiple-testing corrections.

---

## License

Internal research code. No warranty.
