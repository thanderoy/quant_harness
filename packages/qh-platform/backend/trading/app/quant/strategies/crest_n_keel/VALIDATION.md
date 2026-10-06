# `crest_n_keel` — Demo Validation

**Codename:** `crest_n_keel`  ·  **Module:** `quant.strategies.crest_n_keel`
**Environment:** `mt5-test` (demo)  ·  **Magic:** `1100001`  ·  **Symbol:** `XAUUSD`  ·  **TF:** H1
**Status:** deployed to demo — validation accruing.

> These criteria are **locked at deploy**. Do not change them mid-validation —
> doing so turns validation into rationalisation. Adjust only with a written,
> dated rationale below, before the relevant milestone is reached.

---

## Deployment choices (locked)

| Knob | Value | Rationale |
|---|---|---|
| Per-trade risk | **0.5% equity** | Runs alongside ASQS; both directional XAUUSD → same-side exposure can stack. Conservative until portfolio correlation control exists. |
| Drawdown-guard threshold | **15%** | OOS MDD ~15.6%; halts only on tail events worse than the backtest tail. (ASQS uses 8% because its backtested MDD is 5.5%.) |
| Peak-state file | `/var/lib/qhf/peak_hma_stoch_1h.json` | Separate peak per strategy; never shared. |
| Session window | **08:00–17:00 UTC**, by **bar open time** | London+NY. Convention: a bar counts in-session if its *open* hour ∈ [8,17): 08:00 opens in, 17:00 opens out. Applied to the closed bar (`iloc[-2]`) so live matches backtest. |
| Friday cutoff | **no new entries after Fri 15:00 UTC**, by **wall-clock** | Avoids opening late-Friday positions carried over the weekend gap. Wall-clock (not bar) because the risk is about when the position is *opened*. Risk-reducing deviation from backtest if the backtest enters late Friday. |
| Spread filter | **50 pt** | H1 with wide SL/TP → low spread sensitivity; cheap insurance vs news/thin liquidity. |
| Schedule | `HH:01` weekdays (`crontab(minute=1, day_of_week="mon-fri")`) | Fires 1 min after H1 close so the bar is finalised; signal reads `iloc[-2]`. |
| Filling mode | `ORDER_FILLING_IOC` | Resolved centrally in `mt5-api/main.py` from `symbol_info.filling_mode`. |

---

## Tier 1 — Operational acceptance (the deployment is *correct*)

Reviewed at **10 filled trades**. All must pass.

| Metric | Target |
|---|---|
| Trade count (filled) | ≥ 10 |
| Unhandled exceptions in Celery worker | 0 |
| Missed scheduled runs | 0 |
| Duplicate orders (same magic, overlapping) | 0 |
| Orders rejected by broker | < 5% of attempts |
| Naked positions (filled without SL/TP) | 0 |
| Mean fill slippage | ≤ 0.5 × backtest assumption |
| 95th-pct fill slippage | ≤ 2 × backtest assumption |
| Session-filter compliance | 100% (no filled entry with bar open outside 08:00–17:00 UTC) |

**Fail at the 10-trade mark → not operationally accepted.** Diagnose, fix, redeploy, restart the count.

---

## Tier 2 — Statistical acceptance (performance consistent with backtest)

Reviewed at **30 filled trades**. All must pass.

| Metric | Target |
|---|---|
| Trade count | ≥ 30 |
| Realized expectancy / trade | within ±1.5 SE of backtest mean |
| Realized win rate | within ±10 pp of backtest; hard floor > 35% |
| Realized profit factor | ≥ 1.2 |
| Realized max drawdown | ≤ 1.5 × backtest OOS MDD (≈ ≤ 23%) |
| Mean trade duration | within ±50% of backtest median |
| Drawdown halts fired | 0 expected; if fired, the halt was correct (dd ≥ 15%) |

**Fail at N=30 → do not promote to live.** Extend the window, shelve, or open a forensic review spec.

---

## Decision gates

- **10 trades (operational):** pass all Tier 1 → eligible for live at **min lot (0.01)** while Tier 2 accrues. Fail → diagnose & redeploy demo.
- **30 trades (statistical):** pass all Tier 2 → eligible for live at **full sized lots**. Fail → see Tier 2 note.
- **Any time — drawdown halt fires correctly:** live deployment paused; root-cause why drawdown reached 15% (regime change / parameter drift / broker pathology). **Do not auto-resume.**

## Kill criteria

- < 10 trades by **90 days** → trade frequency materially below expectation; investigate (session too tight / signal rare in regime / eval bug).
- < 30 trades by **6 months** → statistical acceptance unachievable in reasonable time; either declare *operationally-validated-only* (with caveat) or shelve.

---

## Review log

| date | milestone | outcome | notes |
|---|---|---|---|
| _deploy_ | criteria locked | — | this document |

> After each milestone, record the outcome here **and** as an `OPERATIONAL_REVIEW`
> event in the research log.

## Running trade table

> Auto-generate from the `Trade` model (magic `1100001`, env `test`) via a small
> management command — manual entry will be skipped.

| trade_n | entry_time | dir | entry | sl | tp | exit_time | exit_price | reason | pnl | slippage | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
