# quant_harness — symbol-agnostic research and execution harness

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
packages/
├── qh-resources/   → import `resources`
│   └── instrument registry, tradability mask, panel, normalisation,
│       indicators, sizing, drawdown guard, broker port
├── qh-strategies/  → import `strategies`
│   ├── instrument-neutral strategy definitions; emit risk units, never lots
│   └── registry.py          # lifecycle; a beat schedule is generated, not written
└── qh-research/    → import `research`
    ├── log.py               # append-only, hash-chained hypothesis register
    ├── pre/                 # signal_edge (E-Ratio), screens — before a backtest
    ├── post/                # dsr, mintrl, sweeps — after the harness runs
    ├── parity/              # migration parity fixtures (T9)
    ├── metrics/             # Sharpe family, PSR/DSR twin, PBO
    ├── validation/          # walk-forward split generators
    ├── reports/             # pre-registered gate evaluator
    ├── engines/             # backtesting.py wrapper and its strategy adapters
    ├── datasets/            # CSV loader and broker cost models
    └── data/                # OHLCV inputs

examples/                    # runnable drivers for the above
tests/                       # repo-level suite; each package also has its own
```

The import-direction contract is `resources ← strategies ← research`, enforced
at AST level in CI (X19). `resources` imports none of the others and is
importable with no network and no Django settings.

---

## Quick start

```bash
# Setup — uv manages the environment and the four workspace packages
uv sync --group test

# Verify on your machine
uv run pytest -q
# expected: 548 passed, 1 skipped — with the out-of-repo data present.
# Without it (and on CI): 524 passed, 25 skipped. See the note below.

# Calibration check (synthetic data)
PYTHONPATH=packages/qh-resources:packages/qh-strategies:packages/qh-research \
  uv run python -m examples.score_a_strategy
# expected: Demo 1 (noise) FAILs gates; Demo 2 (alpha) PASSes
```

If the suite passes and the calibration demo behaves as described, the harness
is trustworthy on your machine.

Two things worth knowing before the commands surprise you:

- **`PYTHONPATH` is needed outside pytest.** The four package paths are set in
  `[tool.pytest.ini_options] pythonpath`, so pytest finds them and nothing else
  does — `examples/` fails with `ModuleNotFoundError: No module named
  'research'` without the prefix above.
- **The skip count depends on data you may not have.** Some parity checks read
  OHLC CSVs and a WMPS checkout that live outside this repo; without them the
  run is 524 passed, 25 skipped, which is what CI sees. `CI_LIMITED` in
  `tests/test_x_coverage.py` names every such case and why.

> Until 2026-09-20 this section said `pip install -r requirements.txt`,
> `python -m unittest discover tests -v` and "Ran 53 tests — OK". Following it
> gave 7 errors on 19 collected tests, and the calibration demo failed to
> import at all.

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
from research.datasets import load_bars

result = load_bars("packages/qh-research/research/data/XAUUSD_H1.csv", expected_timeframe="H1")
print(result.summary_str())
# rows, timeframe, span_years, gaps, warnings...

df = result.df  # DatetimeIndex'd OHLCV DataFrame
```

### Cost model

```python
from research.datasets import PepperstoneXAUUSDCostModel
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
from research.validation import (
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
from research.metrics import dsr_from_trials, pbo
from research.reports import Result, Thresholds, evaluate

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
| Commission (MT5 Razor) | $7 round-turn / lot ($0.07 per 0.01 lot) | Pepperstone Costs and Charges — **but see below** |
| Spread (typical) | ~$0.22 / oz | User-observed; Pepperstone-published range $0.05–$0.30 |
| Triple-swap day | Wednesday rollover | Pepperstone docs |
| Server rollover | 5pm New York / 23:59 server time | Pepperstone docs |
| Swap rates | floating, weekly-updated | Override from MT5 Symbol Specifications |
| Stops level | floor at $0.10/oz (assumed) | Verify in MT5 |

Practical implication: a 0.01 lot intraday round-trip costs roughly $0.29. With
2% risk on a $100 account = $2 per trade, costs are ~14% of risk. Strategy must
overcome this drag before any losses to be profitable.

**Measured 2026-09-20: this account pays no commission at all** (seq=105).
Every one of 358 deals on the live account — five symbols, fourteen months,
including four FX majors where the Razor schedule is unambiguous — carries
commission of exactly 0.00. It is not a reporting artifact: `swap` populates
on the same deals, and 0.03-lot deals would owe $0.105 a side. The account is
not on the Razor schedule, so the $7 row above describes a schedule this
account is not billed under, and the gold dispute below is moot rather than
settled. The constant is deliberately still 7.0: zeroing it improves every
recorded metric, and the measured spread that would pay for the missing
commission (0.17 USD/oz) is not the 0.22 the model assumes, so the two have to
change together or not at all.

The dispute that prompted the measurement, retained for the record:
Pepperstone's Costs and
Charges document says commission is "charged on all FX trades" and that on both
MetaTrader and cTrader the commission on metals "are reflected in the spread
with no separate commission charge" — which would mean XAUUSD carries none of
the $7, and every backtest here over-costs it. Their Razor Gold product page
says the opposite. The value is deliberately left in place: both readings err
the same way, so results are under-stated rather than flattered, and changing
it would silently re-price every metric in the research log. Two further
caveats: the document is Pepperstone **Limited**, while the live account is
**PepperstoneKE**, a different entity; and the $7 is keyed on the **account**
currency, not the traded pair's base currency, so it needs no per-symbol FX
conversion on MT5 (the cTrader schedule differs and does). One read of the
`commission` field on a real deal settles all of it.

---

## Architecture principle

The harness scores returns. It does not run strategies. The reason for the split
is auditability:

```
[Strategy code]  →  per-period returns series  →  [research]  →  pass/fail report
                          (engine-agnostic)
```

Whatever produces the returns — VectorBT for breadth (parameter sweeps),
backtesting.py for depth (path-dependent), MT5 Strategy Tester for ground
truth — is interchangeable. Only the returns matter to the gates.

---

## What's coming

Phases are the rewrite's (`docs/REWRITE.md` §7), not the old per-module
numbering — that table described the pre-rewrite package layout and had been
stale since the T10 rename replaced it.

| Phase | Scope | Status |
|---|---|---|
| 0 | Diagnostic — D1-D9, no code changes | ✅ done |
| 1 | Registry, mask, panel, normalisation, sizing, log schema, parity | ✅ done — 10/10 criteria |
| 2 | Panel harness — `signal_edge` per-instrument across the FX majors | ⏭ next |
| 2b | Universe expansion — non-USD crosses, metals, indices | ⏭ after 2 |
| 3+ | Execution merge, live path | ⏭ not until a mechanism survives 2b |

`docs/STATUS.md` carries the current snapshot and the open items.

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
