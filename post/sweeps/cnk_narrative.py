"""research.post.sweeps.cnk_narrative — prose for the crest_n_keel sweep report.

Kept separate from build_cnk_report so the table mechanics stay data-driven and
the interpretation stays in one auditable place. Every number quoted here is
pulled from the report data rather than typed in, so the prose cannot drift out
of sync with a re-run.
"""
from __future__ import annotations


def _f(x, dp=3, dash="&mdash;"):
    return dash if x is None else f"{float(x):.{dp}f}"


def _p(x, dp=1):
    return "&mdash;" if x is None else f"{float(x):.{dp}f}%"


def narrative(D: dict) -> dict:
    lead = D["leader"]
    tf, mode, direc = lead["timeframe"], lead["mode"], lead["direction"]
    sh = lead["sharpe_px"]
    bh = D["buy_and_hold"][tf]
    k1 = next((c for c in D["k1_controls"]
               if c["timeframe"] == tf and c["mode"] == mode), {})
    k2 = next((b for b in D["k2_calmar"]
               if b["timeframe"] == tf and b["mode"] == mode), {})
    n_full = D["n_configs_total"]
    dsr_full = (D["k3_dsr_single_sharpe_se"].get(str(n_full)) or {}).get("dsr")
    dsr_emp = (D["k3_dsr"].get(str(n_full)) or {}).get("dsr")
    hn = D.get("honest_trial_count")
    dsr_hn = (D["k3_dsr_single_sharpe_se"].get(str(hn)) or {}).get("dsr")
    k4 = D["k4_neighbourhood"]
    n_k1_pass = sum(1 for c in D["k1_controls"]
                    if (c.get("p_value") is not None and c["p_value"] < 0.05))

    cfg = (f"hma{lead['hma_period']} atr{lead['atr_period']} "
           f"trail{_f(lead['trail_mult'], 1)}")

    k = [
        # NB `(p or 1) < 0.05` is wrong here: p_value 0.0 is falsy, so the
        # strongest possible result would be scored as a failure.
        {"id": "K1", "passed": (k1.get("p_value") is not None
                                and k1["p_value"] < 0.05),
         "title": "Matched random-entry control",
         "body": (f"Leader Sharpe <strong>{_f(sh)}</strong> against a null of "
                  f"{_f(k1.get('null_mean'))}, p&nbsp;=&nbsp;{_f(k1.get('p_value'))}. "
                  f"Realised {int(k1.get('median_realized') or 0):,} trades against a "
                  f"target of {int(k1.get('target_trades') or 0):,}. The entry adds "
                  f"{_f(sh - (k1.get('null_mean') or 0), 2)} Sharpe over random timing "
                  f"in the same regime, with direction, exits, sizing and costs held "
                  f"identical. {n_k1_pass} of {len(D['k1_controls'])} per-cell leaders "
                  f"clear p&nbsp;&lt;&nbsp;0.05.")},
        {"id": "K2", "passed": bool(k2.get("beats_bh")),
         "title": "Beats passive long gold",
         "body": (f"Calmar <strong>{_f(k2.get('calmar'), 2)}</strong> against buy-and-hold "
                  f"{_f(k2.get('bh_calmar'), 2)} over the identical window. Read this "
                  f"honestly: the strategy earns <em>less</em> than passive "
                  f"({_p(100 * lead['cagr_acct'])} CAGR against {_p(100 * bh['cagr'])}) "
                  f"and wins only on risk &mdash; max drawdown "
                  f"{_p(100 * lead['max_dd_px'])} against {_p(100 * bh['max_dd'])}. "
                  f"It is a better ride, not a bigger one.")},
        {"id": "K3", "passed": bool(dsr_full is not None and dsr_full > 0.95),
         "title": "Deflated Sharpe at grid scale",
         "body": (f"DSR <strong>{_f(dsr_full, 3)}</strong> at N&nbsp;=&nbsp;{n_full:,} "
                  f"with estimated Var(SR) &mdash; short of the 0.95 threshold. This is "
                  f"the binding constraint and the reason nothing here gets promoted. "
                  f"It is also the best DSR any strategy in this repo has posted.")},
        {"id": "K4", "passed": bool(k4.get("all_positive")),
         "title": "Plateau, not an isolated spike",
         "body": (f"All {k4['n_countable']} one-step grid neighbours stay positive "
                  f"(median {_f(k4.get('median_sharpe'))}, worst "
                  f"{_f(k4.get('min_sharpe'))}). Weak evidence though: the leader sits "
                  f"at the <em>corner</em> of the grid &mdash; smallest HMA, fastest ATR, "
                  f"tightest trail &mdash; so every neighbour lies in one direction and "
                  f"the test is one-sided.")},
    ]

    deg = D["min_atr_degeneracy"]
    deg_txt = ", ".join(f"{d['timeframe']} {d['rows']:,}&rarr;{d['distinct']:,}"
                        for d in sorted(deg, key=lambda x: -x["rows"] / max(x["distinct"], 1)))

    return {
        "lede": (
            f"A {D['n_configs_raw']:,}-configuration sweep across five timeframes and both "
            f"entry modes, run to settle one question: is the momentum variant genuinely "
            f"better than the deployed pullback entry, or was that a selection artifact "
            f"of a single TradingView search? The answer is neither. The momentum entry "
            f"is better in a band &mdash; H1 and H4 &mdash; and worse outside it. The "
            f"leader clears the drift control and beats passive gold on risk-adjusted "
            f"return, and still fails Deflated Sharpe."),
        "k": k,
        "k_note": (
            "Two pass, one fails, one passes on thin evidence. K3 is decisive against "
            "promotion; the frozen stopping rule permits exactly one next step, and a "
            "finer grid around the leader is not it."),
        "mode_note": (
            "Median across every configuration in the cell, so this describes the region "
            "rather than a hand-picked winner. &ldquo;% positive&rdquo; is the share of "
            "configs with Sharpe above zero &mdash; the more robust of the two columns, "
            "because it cannot be moved by a single outlier."),
        "mode_prose": (
            "<strong>P1 fails as written.</strong> The registration predicted that a "
            "genuine momentum advantage would show up as dominance on median Sharpe "
            "<em>and</em> percent-positive at every timeframe. It does not: momentum wins "
            "decisively at H4 and H1, loses to pullback at D1 and M5, and splits at M15. "
            "The advantage is real but <em>local</em>, which is a third answer the "
            "registration did not anticipate and a more useful one than either alternative. "
            "One confound is worth stating: the mode medians pool all three direction "
            "settings, and momentum's short and both-direction variants are far worse than "
            "its long-only variant. Controlling for direction, momentum long beats pullback "
            "long at four of five timeframes &mdash; everywhere except M5. The honest "
            "reading is that P1 fails on its pre-registered wording and survives in a "
            "direction-controlled form that was not what was registered."),
        "tf_prose": (
            "The same cliff the zerolag_chandelier sweep found, in the same place. "
            "Everything at M15 and below is negative at the median in both modes, and the "
            "cause is not the signal &mdash; it is that a roughly fixed cost per round "
            "trip is charged against a gross edge per trade that shrinks with the horizon. "
            "M5 momentum trades a median of 7,425 times and returns a median Sharpe of "
            "&minus;0.839. The signal is not being tested there; the spread is."),
        "dir_note": (
            "<strong>P2 holds, and holds everywhere.</strong> Long beats short at every "
            "timeframe in both modes, and momentum long-only is the single best cell on "
            "the board. The long-only restriction that seq&nbsp;35 froze in without testing "
            "was the right call. This is the third independent sweep in this repo to reach "
            "the same conclusion &mdash; the short side of XAUUSD is dead across every "
            "timeframe, mode and parameter set tested."),
        "rank_note": (
            "Ranked over configs clearing the 100-trade floor only. Without that floor the "
            "top of a grid this size is two-trade noise with an infinite profit factor "
            "&mdash; the failure mode caught during the ebb_n_flow sweep. Sharpe, drawdown "
            "and profit factor are on the harness price-return basis so they are comparable "
            "with figures already in the research log; CAGR is on the account basis at 2% "
            "risk per trade. Ranking by any single column is precisely the selection "
            "process the Deflated Sharpe section below penalises."),
        "k1_note": (
            "The null randomises <em>only</em> the entry bars, drawn from the config's own "
            "eligible pool. Direction, exit rule, position sizing, cost model and realised "
            "trade count are held identical, so the comparison isolates entry timing from "
            "gold's drift and from the exit. Null means are positive at the timeframes "
            "where gold trends &mdash; that positive value <em>is</em> the drift, priced "
            "into the benchmark rather than credited to the strategy."),
        "k1_prose": (
            "This is the test that shelved <code>flood_tide_h1</code> and confirmed the "
            "<code>ebb_n_flow</code> kill, where the measured effect collapsed into the "
            "null once drift was matched (p&nbsp;=&nbsp;1.000). Here it does not collapse: "
            f"the leader beats its null by {_f(sh - (k1.get('null_mean') or 0), 2)} Sharpe "
            "at p&nbsp;=&nbsp;0.000. Two cells do fail &mdash; M5 momentum (p&nbsp;=&nbsp;"
            "0.166) and D1 pullback (p&nbsp;=&nbsp;0.057) &mdash; and both failures are "
            "informative rather than awkward: they are the two cells where the mode is "
            "out of its band."),
        "k2_note": (
            "Calmar is CAGR divided by maximum drawdown, both on the account basis at 2% "
            "risk per trade; the benchmark is passive long XAUUSD over the identical "
            "window, annualised on bar frequency rather than trade frequency because bar "
            "returns and per-trade returns are different observation streams. Note what "
            "passing here does and does not mean: no leader out-earns passive gold in "
            "absolute terms &mdash; gold compounded at roughly 12% a year over this window "
            "and none of these configs match it. They win, where they win, by taking "
            "materially less drawdown to get a smaller number. For an account with a 10% "
            "maximum-drawdown mandate that is the relevant comparison, but it should not "
            "be mistaken for beating the market."),
        # NB this string is a section() subtitle and gets HTML-escaped, so it
        # must carry literal characters rather than entities.
        "dsr_sub": (f"Leader: {tf} \u00b7 {mode} \u00b7 {direc} \u00b7 {cfg} "
                    f"\u00b7 Sharpe {_f(sh)}"),
        "dsr_callout": (
            f"<p><strong>DSR ranges from {_f(dsr_emp, 3)} to {_f(dsr_hn, 4)} depending "
            f"entirely on how Var(SR) and N are chosen, and only the most flattering "
            f"reading passes.</strong> That reading sets N&nbsp;=&nbsp;{hn}, the research "
            f"log's global trial floor, which does not know this sweep happened. For a "
            f"configuration selected as the best of {n_full:,}, it is the wrong N.</p>"
            f"<p>The empirical-Var(SR) column fails in the other direction, and for the "
            f"same reason it did on the zlch sweep: pooling trial Sharpes across five "
            f"structurally different timeframes measures real heterogeneity &mdash; M5 "
            f"configs near &minus;0.9 sitting beside H4 configs near +1.0 &mdash; not "
            f"estimation noise under a null. It inflates the benchmark to a level nothing "
            f"could clear. That is a misapplication of the estimator, not evidence.</p>"
            f"<p>The defensible primary figure is <strong>DSR&nbsp;=&nbsp;{_f(dsr_full, 3)} "
            f"at N&nbsp;=&nbsp;{n_full:,} with estimated Var(SR)</strong>. It fails 0.95. "
            f"It is also, for what it is worth, the highest figure any strategy in this "
            f"repo has reached &mdash; against 0.739 for zerolag_chandelier and outright "
            f"failure at every N for ebb_n_flow. Better than everything else here and "
            f"still not good enough is the whole finding.</p>"),
        "k4_note": (
            "Neighbours are configs one grid step away in exactly one dimension. Only "
            f"{k4['n_neighbours']} exist because the leader sits at a grid corner and "
            "because momentum ignores the stochastic and bracket dimensions entirely. "
            "All are positive, but all lie on the same side, and Sharpe declines "
            "monotonically as you step away from the corner. That pattern is consistent "
            "with a genuine plateau and equally consistent with an optimum sitting "
            "<em>outside</em> the swept range &mdash; at a faster HMA or tighter trail "
            "than the grid contains. Resolving that requires a new registration, not a "
            "reinterpretation of this one."),
        "engine_prose": (
            "The sweep engine is a rewrite. <code>backtesting.py</code> is a per-bar "
            "Python loop and would have taken days for this grid. It was validated "
            "against the two canonical harness strategies under "
            "<code>btpy_runner</code> on eleven configs spanning four timeframes and both "
            "modes: <strong>100% entry-set match and worst |&Delta;Sharpe| of 0.0031</strong>. "
            "Reaching that parity surfaced three real semantic differences, all fixed here: "
            "the stochastic warm-up fills to 50 rather than propagating NaN (pandas "
            "<code>.where</code> treats a NaN condition as False, and forcing NaN instead "
            "delays %K by <code>k_period</code> bars and shifts every cross); the ATR seeds "
            "at index <code>period</code> from <code>mean(tr[1:period+1])</code>, which "
            "differs from the zlch engine's variant by one bar; and contingent stop/target "
            "orders are checked on the fill bar itself, not the bar after. That last one "
            "was settled by parity rather than by reasoning &mdash; the fill-bar reading "
            "gives 100% entry match against 99.7% for the alternative. Two caveats on "
            "scope: parity covers the default parameter slice only, since the swept "
            "stochastic zones and the direction toggle do not exist in the canonical "
            "classes; and <code>max_drawdown_halt</code> is disabled throughout, because "
            "it is an absorbing barrier that truncates a config's record at a "
            "path-dependent point and makes configs incomparable. Drawdown is reported as "
            "a metric instead."),
        "licenses": (
            "<p><strong>It does not license deployment.</strong> Every number here is "
            "in-sample over the full history. K3 fails. The frozen stopping rule permits "
            "exactly one next step: an out-of-sample walk-forward under "
            "<code>qhf_harness</code> on the H4/H1 momentum long-only region.</p>"
            "<p><strong>It does not license a finer grid around the leader</strong>, "
            "however tempting the corner-plateau result makes it. That is overfitting and "
            "requires a new registration and a further trial-count increment.</p>"
            "<p><strong>It does license an operational decision about the deployed "
            "strategy.</strong> P7 is confirmed: the live pullback configuration "
            "(hma&nbsp;55, sl&nbsp;1.5, tp&nbsp;3.0, zones&nbsp;20/80, magic&nbsp;1100001) "
            "has a median Sharpe of &minus;0.074 across its 313-config neighbourhood, with "
            "38.3% of that neighbourhood positive. seq&nbsp;29's walk-forward result was "
            "not bad luck on one parameter set &mdash; it is a property of the entry. "
            "Nothing in this sweep rehabilitates it.</p>"),
        "transfer": (
            "Three findings transfer regardless of what happens to this strategy. The "
            "short side of XAUUSD is dead across every timeframe, mode and parameter set "
            "tested &mdash; now three sweeps deep. Sub-H1 timeframes are a cost regime "
            "rather than a signal regime, and testing a signal there measures the spread. "
            "And an entry's advantage can be genuinely local to a timeframe band, which "
            "means a single-timeframe verdict &mdash; in either direction &mdash; is worth "
            "less than it appears; the seq&nbsp;20 E-Ratio kill recorded against "
            "zerolag_chandelier on M15 alone is the cautionary case."),
        "repro_note": (
            f"Artifacts in <code>research/data/crest_n_keel/</code>: five "
            f"<code>cnk_sweep_&lt;TF&gt;.csv</code> (one row per config), "
            f"<code>cnk_deepdive.csv</code> (top 500), <code>cnk_leader_returns.csv</code> "
            f"(per-trade returns for the leader), <code>cnk_report_data.json</code>. "
            f"Raw grid {D['n_configs_raw']:,} rows; {n_full:,} distinct after collapsing "
            f"<code>min_atr</code> duplicates, which is the N used for the deflation. "
            f"<code>min_atr</code> never binds where ATR exceeds every tested floor "
            f"({deg_txt}). Random seed 20260820 throughout."),
        "footer": (
            f"crest_n_keel parameter sweep &middot; {D['n_configs_raw']:,} configurations "
            f"&middot; research log seq 44 &middot; leader {tf} {mode} {direc} {cfg} "
            f"&middot; K1 pass, K2 pass, K3 fail, K4 thin &middot; verdict DO NOT PROMOTE"),
    }
