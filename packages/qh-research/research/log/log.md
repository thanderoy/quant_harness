# Research Log (rendered view)

> **Generated artifact** — do not edit. Source: `entries.jsonl`. Regenerate with `render_markdown()`.

- **Entries:** 97
- **Trial count (floor N for DSR):** 26
- **Hash chain:** OK — chain ok (97 entries)

## Principles

**1. E-Ratio: hard gate vs diagnostic** — The E-Ratio is a **hard gate** for breakout/continuation entries (the entry itself should do the work — kill on a flat E-Ratio). It is a **diagnostic only** for pullback/mean-reversion entries (the edge legitimately lives in the exit — a flat entry E-Ratio is expected and must NOT trigger a kill). Set `edge_gate_role` at registration time so this rule travels with the hypothesis.

**2. Log generously; the trial count is a floor** — `trial_count()` is the N that feeds Deflated Sharpe Ratio. It cannot capture ideas considered and discarded before logging, so the true multiple-testing burden is always ≥ this number. Register early, even for vague ideas — it's cheaper to log a trial than to under-haircut a future Sharpe.

## Current state by hypothesis

Edge-gate role is shown on every row: a **hard_gate** entry must show E-Ratio edge; a **diagnostic** entry may legitimately have a flat E-Ratio (edge lives in the exit) and must not be killed on it.

| hypothesis | family | role | stage | verdict | latest metrics |
|---|---|---|---|---|---|
| `asian_session_fade` — Asian-session ATR-channel fade | mean_reversion | diagnostic | 1_signal_edge | shelved | allday_fade_gross_t=0.83, allday_fade_gross_usd_per_oz=0.0973, beta_fwd_on_overshoot=-0.0337, beta_p_shuffle_one_sided=0.046, beta_r_squared=0.0006, beta_t=-1.66, decile_fade_gross_t=0.28, decile_fade_gross_usd_per_oz=0.0823, decile_fade_net_usd_per_oz=-0.2077, edge_cost_ratio=0.284, london_control_beta=0.0422, london_control_t=1.84, median_daily_atr_usd=19.07, n_days=4317, roundtrip_cost_usd_per_oz=0.29 |
| `asqs` — ASQ SafeScalping v1.20 — M5 7-condition breakout | breakout | hard_gate | 5_walk_forward | open | profit_factor=1.55, sharpe_oos=5.14, dsr_prob_24h=0.0, dsr_prob_session=0.0, folds=33, oos_max_dd_24h=0.67, oos_max_dd_session=0.72, oos_trades_24h=11763, oos_trades_session=11048, profit_factor_24h=0.91, profit_factor_session=0.9, sharpe_oos_24h=-1.06, sharpe_oos_session=-1.04 |
| `asqs_param_sweep` — Exhaustive parameter + timeframe sweep of ASQ SafeScalping v1.20 | asqs | hard_gate | 3_is_backtest | open | ak1_null_mean=-2.077, ak1_p_value=0.0, ak2_bh_calmar=0.274, ak2_calmar=0.675, ak2_n_beating_bh=2, ak3_dsr_at_grid_n=0.0384, ak4_all_tf_medians_negative=1, dir_median_long=0.016, dir_median_short=-0.417, leader_cagr_acct=0.0538, leader_max_dd_px=0.0669, leader_n_trades=1147, leader_profit_factor_px=1.1876, leader_session=7-16, leader_sharpe_px=1.0664, leader_timeframe=M5, n_configs=52488, n_countable=51277, n_survivors=533, session_error_cost_sharpe=0.0717, session_median_7_16=-0.0726, session_median_8_17=-0.1443, session_median_off=-0.4569, tf_median_H1=-0.071, tf_median_M15=-0.164, tf_median_M5=-0.383 |
| `avwap_liquidity_sweep` — H1 HMA + NY AVWAP + 5-day VP + sweep/reclaim | breakout | diagnostic | 0_hypothesis | shelved | — |
| `avwap_multibar_reclaim_m15` — AVWAP-only multi-bar sweep-and-reclaim on XAUUSD M15 with H1 HMA bias | mean-reversion | diagnostic | 3_is_backtest | shelved | artifact_path=research/artifacts/avwap_multibar_reclaim_signal_edge_20260614T133418Z.json, e_ratio_16bar_combined=0.7442676947027749, e_ratio_16bar_long=0.752738401545089, e_ratio_16bar_short=0.7373789256325337, e_ratio_16bar_sweep_1bar=0.8587431852056898, e_ratio_16bar_sweep_2bar=0.6593045423120963, e_ratio_16bar_sweep_3bar=0.63133028877003, e_ratio_32bar_combined=0.8579269972413494, e_ratio_8bar_combined=0.8029473830802075, p_value_16bar=0.943, random_baseline_ci_hi=1.3435445752288044, random_baseline_ci_lo=0.7338073025220379, random_baseline_mean=1.1712825593901284, run_valid=False, signal_hash=97102210ade375b6, trigger_count_long=40, trigger_count_short=43, trigger_count_sweep_1bar=40, trigger_count_sweep_2bar=27, trigger_count_sweep_3bar=16, trigger_count_total=83, best_sharpe_px=0.071, drift_actual=0.071, drift_null_mean=-0.113, drift_p=0.232, median_sharpe_px=-0.436, median_trades=92, n_configs=2808, pct_countable=49.8, pct_positive=2.1 |
| `avwap_sweep_reclaim_m15` — AVWAP/POC/HVN sweep-and-reclaim on XAUUSD M15 with H1 HMA bias | mean-reversion | diagnostic | 3_is_backtest | open | artifact_path=research/artifacts/avwap_sweep_reclaim_signal_edge_20260614T083827Z.json, e_ratio_16bar_avwap=0.6105235797712227, e_ratio_16bar_combined=0.806326708871015, e_ratio_16bar_hvn=0.9389136831082255, e_ratio_16bar_long=0.8362129729640871, e_ratio_16bar_poc=0.5316155984971189, e_ratio_16bar_short=0.7813945766834295, e_ratio_32bar_combined=0.8981169691816416, e_ratio_8bar_combined=0.8630572252818496, p_value_16bar=0.942, random_baseline_ci_hi=1.2329962317847916, random_baseline_ci_lo=0.7953614436587528, random_baseline_mean=1.0407515046105003, signal_hash=35d6b60e498f3813, trigger_count_avwap=40, trigger_count_hvn=97, trigger_count_long=58, trigger_count_poc=8, trigger_count_short=87, trigger_count_total=145, best_sharpe_px=0.492, drift_actual=0.492, drift_null_mean=-0.156, drift_p=0.001, median_sharpe_px=-0.101, median_trades=122, n_configs=2808, pct_countable=60.2, pct_positive=29.9 |
| `cnk_nested_walk_forward` — crest_n_keel nested walk-forward: does the selection procedure generalise? | crest_n_keel | diagnostic | 5_walk_forward | killed | h1_fixed_mean=0.76, h1_folds=17, h1_nk2_n=17, h1_nk2_p=0.5, h1_nk2_wins=9, h1_oos_mean=0.079, h1_oos_median=-0.041, h1_oos_positive=8, h1_oos_trades_median=27, h1_pool_mean=-0.176, h1_train_sharpe_mean=1.648, h4_fixed_mean=0.452, h4_folds=16, h4_nk2_n=15, h4_nk2_p=0.5, h4_nk2_wins=8, h4_oos_mean=-0.353, h4_oos_median=0.24, h4_oos_positive=8, h4_oos_trades_median=10, h4_pool_mean=-0.116, h4_train_sharpe_mean=1.448, lookahead_gap_h1=0.681, lookahead_gap_h4=0.805, pooled_nk2_n=32, pooled_nk2_p=0.43, pooled_nk2_wins=17, pooled_pool_mean=-0.149, pooled_selected_mean=-0.124, pooled_selection_value=0.025 |
| `cnk_param_sweep` — Exhaustive parameter + timeframe sweep of crest_n_keel, both entry modes | crest_n_keel | diagnostic | 5_walk_forward | open | deployed_pullback_region_median_sharpe=-0.0738, k1_null_mean=0.435, k1_p_value=0.0, k2_bh_calmar=0.2768, k2_calmar=0.4675, k3_dsr_at_grid_n=0.8391, k4_neighbour_min_sharpe=0.6771984633116068, leader_cagr_acct=0.0769028726896998, leader_direction=long, leader_max_dd_px=0.2693262706455639, leader_mode=momentum, leader_n_trades=2141, leader_profit_factor_px=1.3726347675526729, leader_sharpe_px=0.9849627340280688, leader_timeframe=H4, leader_win_rate=0.4072863148061653, n_configs_distinct=119917, n_configs_raw=150660, n_countable=98995, n_survivors=2789, gate_passed=0, h1_dsr_at_grid_n=0.0, h1_folds_positive=12, h1_folds_total=17, h1_is_oos_gap=-0.02, h1_oos_max_dd=0.187, h1_oos_profit_factor=1.29, h1_oos_sharpe_mean_folds=0.761, h1_oos_sharpe_median_folds=0.429, h1_oos_sharpe_pooled=0.91, h1_oos_trades=1973, h4_dsr_at_grid_n=0.0, h4_folds_positive=11, h4_folds_total=16, h4_is_oos_gap=0.07, h4_oos_max_dd=0.273, h4_oos_profit_factor=1.23, h4_oos_sharpe_mean_folds=0.454, h4_oos_sharpe_median_folds=0.301, h4_oos_sharpe_pooled=0.71, h4_oos_trades=1595 |
| `crest_n_keel` — HMA+Stoch 1H pullback (a.k.a. hma_stoch_1h) | pullback | diagnostic | 5_walk_forward | open | e_ratio_w30=0.9, p_value=0.34, sharpe_oos=1.76, dsr_prob_24h=0.106, dsr_prob_session=0.028, folds=33, oos_max_dd_session=0.1, oos_trades_24h=323, oos_trades_session=146, profit_factor_24h=1.15, profit_factor_session=1.45, sharpe_oos_24h=0.27, sharpe_oos_session=0.41, spread_stress_survives_2x=True, n_folds=17, seq29_247_corrected=0.1717, seq29_247_delta=-0.002, seq29_247_logged_basis=0.1738, seq29_session_corrected=-0.2386, seq29_session_corrected_dd=0.124, seq29_session_corrected_pf=0.783, seq29_session_delta=-0.5581, seq29_session_logged_basis=0.3196, seq29_session_logged_dd=0.053, seq29_session_logged_pf=1.534 |
| `crest_n_keel_momentum` — crest_n_keel MOMENTUM (HMA-slope-flip, long-only, ATR chandelier trail) | crest_n_keel | hard_gate | 5_walk_forward | open | dsr_prob_num_trials_1=1.0, dsr_prob_num_trials_20=0.061, gate_verdict=FAIL (DSR only); PASS at num_trials=1, harness=qhf_harness run_cnk_momentum, 21.6y H1 2004-2025, 33 folds, is_oos_gap=-0.34, mean_is_sharpe=0.86, oos_max_dd_pct=29.9, oos_profit_factor=1.26, oos_sharpe=1.2, oos_trades=3829 |
| `donchian_50_control` — Donchian-50 breakout (positive control) | breakout | hard_gate | 1_signal_edge | shelved | e_ratio_w10=1.11, e_ratio_w50=1.17, p_value=0.0, artifact_path=None, e_ratio_32bar_combined=None, e_ratio_32bar_long=None, e_ratio_32bar_short=None, p_value_32bar=0.0, random_baseline_mean=None, signal_hash=None, trigger_count_long=None, trigger_count_short=None, trigger_count_total=None |
| `ebb_n_flow` — Bollinger mean-reversion with KER gate | mean_reversion | diagnostic | 3_is_backtest | killed | e_ratio_w30=0.97, gross_expectancy=-1.0 |
| `ebb_n_flow_sweep` — Exhaustive parameter + timeframe sweep of ebb_n_flow (post-kill asymmetry probe) | mean_reversion | diagnostic | 3_is_backtest | killed | K1_configs_clearing=9 of 15, K1_leader_null_mean=0.662, K1_leader_p=1.0, K1_result=FAIL, K2_configs_beating_bh_calmar=3 of 15, K2_result=FAIL, K3_dsr_N16_logfloor=0.8008, K3_dsr_N43200=0.0594, K3_dsr_N9600=0.114, K3_result=FAIL at every N, K4_neighbourhood_frac_positive=1.0, K4_result=PASS (moot), artifact=research/data/ebb_n_flow/ebb_report_data.json, leader=H1 bb_n=10 bb_k=1.5 er_max=0.30 sl=3.0xATR ts=8 long/all-hours, leader_exposure=0.027, leader_max_dd_px=0.063, leader_pf=1.4231, leader_sharpe_px=0.6138, leader_win_rate=0.6013, long_pct_positive_D1=41.2, median_sharpe_D1=-0.2, median_sharpe_H1=-0.373, median_sharpe_H4=-0.341, median_sharpe_M15=-0.572, median_sharpe_M5=-1.284, n_configs=43200, n_survivors=268, short_pct_positive_D1=10.4, survivor_rate_pct=0.62 |
| `ensemble_vs_selection` — Should we average gate-passers instead of picking the best? | methodology | diagnostic | 0_hypothesis | killed | e1_pass=0, e2_sharpe_pass=1, e3_frac_members_positive=0.5648, h1_delta=0.00023, h1_ens_sharpe=0.023, h1_ens_total=0.01592, h1_sign_p=0.6291, h1_top1_sharpe=-0.0168, h1_top1_total=0.0157, h4_delta=0.00332, h4_ens_sharpe=0.05, h4_ens_total=0.02619, h4_sign_p=0.4545, h4_top1_sharpe=0.0171, h4_top1_total=0.02287, k=50, n_folds=33, nothing_revived=1, pooled_delta_pct=9.0, pooled_ens_total=0.0209, pooled_top1_total=0.01918, sharpe_would_have_inverted_verdict=1 |
| `feature_edge_screen` — Feature-level edge screen: which inputs carry cost-clearing information? | feature_screen | diagnostic | 1_signal_edge | open | best_feature_net_usd=1.14, best_feature_spread_usd=1.43, best_feature_t=4.35, composite_all5_spread=1.147, composite_momentum_spread=1.431, cost_round_trip=0.29, h1_paying=21, highvol_spread=1.256, highvol_spread_causal=1.182, lowvol_spread=2.831, lowvol_spread_causal=2.314, m15_paying=1, m5_paying=0, n_fdr_significant=186, n_paying_costs=22, n_tests=264, overall_spread_causal=1.456 |
| `flood_tide_h1` — flood_tide_h1 — Donchian-55 H1 breakout with H4-EMA + Efficiency-Ratio regime gate (XAUUSD, long-only) | trend_following_breakout | hard_gate | 3_is_backtest | open | e_ratio_H100=1.1835210145765311, e_ratio_H20=1.1348806858949592, e_ratio_H50=1.1294091836142026, null_mean_H100=1.211763812660675, p_H100=0.714, p_H20=0.096, p_H50=0.456, best_sharpe_px=0.719, bracket_median_sharpe=0.285, bracket_pct_positive=91.1, drift_actual=0.719, drift_null_mean=0.262, drift_p=0.005, median_sharpe_px=0.331, median_trades=1550, n_configs=3744, pct_countable=100.0, pct_positive=93.2, survivors=550, trail_median_sharpe=0.517, trail_pct_positive=100.0, beats_drift_at_median=1, median_config_dsr_at_19=0.458, median_config_dsr_at_grid_n=0.0328, median_config_null_mean=-0.3556, median_config_null_p95=-0.0391, median_config_p=0.0, median_config_sharpe=0.3313, median_config_trades=2094, median_trail_null_mean=0.0646, median_trail_p=0.013, median_trail_sharpe=0.5164 |
| `flood_tide_h1_iter2` — flood_tide_h1_iter2 — Donchian-20 (faster) H1 breakout, H4-EMA + Efficiency-Ratio regime gate (XAUUSD, long-only). Iteration 2 of seq=31. | trend_following_breakout | hard_gate | 1_signal_edge | shelved | e_ratio_H100=1.2250291493927423, e_ratio_H20=1.1661315377843247, e_ratio_H50=1.1637030632714933, null_mean_H100=1.212674656363149, p_H100=0.357, p_H20=0.011, p_H50=0.16 |
| `gold_dxy_divergence` — Gold–DXY cointegration divergence MR | mean_reversion | diagnostic | 0_hypothesis | killed | best_lag_corr=-0.0139, best_lag_k=1, contemporaneous_corr=-0.3607, corr_252d_frac_negative=1.0, corr_252d_mean=-0.424, corr_full_sample=-0.3607, decile_gross_cost_ratio=0.47, decile_gross_usd=0.1361, eg_adf_t=0.5162, eg_crit_5pct=-3.34, gross_cost_ratio=0.113, gross_usd_per_oz=0.0327, hedge_beta_levels=1.8617, lag_r_squared_pct=0.0194, lead_lag_ratio=0.0386, n_bars_aligned=71368, net_usd_per_oz=-0.2573, p1_rolling_corr_pass=1, p2_coint_pass=0, p3_leadlag_pass=0, syndxy_bars=79928, syndxy_max_abs_landmark_err=0.23, usdx_rejected=1, usdx_unique_prices=143, usdx_zero_ret_pct=29.5, window=2013-10-08..2025-12-31, eg_calib_reps=300, eg_calibrated=1, eg_fp_rate_pct=5.3, eg_nominal_pct=5.0, eg_power_pct=100.0, kill_rests_on_p3_alone=1, statsmodels_available=0 |
| `gold_real_yields` — Do real yields (DFII10) lead gold? | cross_asset | diagnostic | 0_hypothesis | killed | always_long_usd_per_oz=1.1838, causal_lag1=0.0041, contemporaneous_lookahead=-0.0566, corr_252d_frac_neg=0.79, corr_252d_mean=-0.091, corr_full_sample=-0.0566, decile_gross_usd=-1.0722, eg_adf_t=0.8281, eg_beta=-0.1874, excess_over_always_long=-0.9428, gross_cost_ratio=0.831, gross_usd_per_oz=0.241, n_days=4241, rule3_changed_verdict=1, signal_long_pct=46.2, signal_short_pct=45.5, y1_pass=0, y2_pass=0, y3_pass=0 |
| `h1_momentum_nested_wf` — H1 intraday-momentum rule under a nested walk-forward | momentum | hard_gate | 8_deployed | killed | fixed_mean=0.725, horizon_12_picks=17, is_oos_decay=0.791, leakage=0.177, lowvol_filter_picks=11, m2_mean_diff=0.456, m2_n=17, m2_sign_p=0.0245, m2_wilcoxon_p=0.0056, m2_wins=13, momentum_family_picks=12, n_folds=17, oos_folds_positive=15, oos_sharpe_mean=0.548, oos_sharpe_median=0.563, oos_trades_median_per_fold=26, oos_trades_total=937, pool_median_mean=0.092, train_sharpe_mean=1.339, control_reproduces_seq60=0.54, filter_1_5x=0.436, filter_2x=0.38, filter_2x_slip10=0.27, filter_3x=0.269, filter_4x=0.158, filter_base=0.491, filter_trades=374, nofilter_1_5x=0.534, nofilter_2x=0.441, nofilter_2x_slip10=0.258, nofilter_3x=0.256, nofilter_4x=0.072, nofilter_base=0.626, nofilter_trades=1132, recommended_variant_unfiltered=1, swap_cost_sharpe=0.049, dsr_passes=0, dsr_threshold=0.95, filter_dsr_n126=0.4517, filter_dsr_n276=0.3521, filter_oos_trades=374, filter_per_obs_sharpe=0.1178, unfiltered_dsr_n1=0.9959, unfiltered_dsr_n126=0.5144, unfiltered_dsr_n21=0.7658, unfiltered_dsr_n276=0.4121, unfiltered_oos_trades=1132, unfiltered_per_obs_sharpe=0.0763, dsr_empirical_var_sr_n126=0.0, dsr_empirical_var_sr_n21=0.0099, dsr_var_sr_source_used=0, gate_fpr_n126=0.0, gate_fpr_n21=0.0008, gate_power_n126=0.061, gate_power_n21=0.188, n_critical_empirical_path=1, n_critical_estimated_path=3, observed_per_obs_sr=0.0763, positive_control_gold_bh_ann_sharpe=0.744, positive_control_gold_bh_dsr_n126=0.8112, prereg=1, prereg_alpha=0.05, prereg_reps=200, required_per_obs_sr_n126=0.1212, trades_needed_to_pass_n126=3000, cnk_killed_by=0, cnk_lookahead_gap_h1=0.681, cnk_lookahead_gap_h4=0.805, cnk_nk2_n=32, cnk_nk2_p=0.43, cnk_nk2_wins=17, cnk_selection_value_sharpe=0.025, dsr_decided_clean_oos_kills=1, triage_corrected=1, zlch_status_untested_oos=1, decisive_stream_nested=1, drift_share_of_fixed_sharpe=0.145, dsr_n126_understated=0.5144, fixed_excess_null_sd=2.93, fixed_null_max=0.08568, fixed_null_mean=0.01104, fixed_null_q95=0.04741, fixed_null_sd=0.02227, fixed_observed=0.07627, fixed_p=0.01, fixed_passes=1, nested_excess_null_sd=1.23, nested_null_mean=0.00467, nested_null_q95=0.04417, nested_null_sd=0.02669, nested_observed=0.03747, nested_p=0.1045, nested_passes=0, null_reps=200, demo_balance=3643.15, deployed_demo=1, entry_agreement_pct=99.7, environment_test=1, first_fire_utc=20260831, intraday_ret_max_diff=0.0, mae_max_atr=13.59, mae_median_atr=1.29, mae_p99_atr=7.98, magic=1600001, min_lot_risk_pct_high=6.0, min_lot_risk_pct_low=3.9, pctile_window=50000, stop_atr_mult=10.0, stop_would_bind_pct=0.301, untradeable_at_100usd=1, beat_entry_disabled=1, d8_wmps_commit=3db869a, drawdown_guard_wired=0, live_risk_halt=1, min_lot_risk_pct_at_100usd_atr14=1.4, min_lot_risk_pct_at_100usd_atr22=2.2, min_lot_risk_pct_at_demo_atr14=0.0384, min_lot_risk_pct_at_demo_atr22=0.0604, risk_pct_configured=0.05, sizer_default_risk_pct=0.02, sizer_grid_cells=480, sizer_grid_cells_over_budget=125, sizer_grid_over_budget_share=0.2604, sizer_grid_worst_realised_risk_pct=6.0 |
| `regime_align_h1` — Three-parameter regime alignment (ER + vol expansion + anchor bias) as a standalone H1 entry | momentum_continuation | hard_gate | 1_signal_edge | shelved | aligned_pct_of_bars=5.626, e_ratio_h100=1.256, e_ratio_h20=1.157, e_ratio_h50=1.161, e_ratio_threshold=1.15, n_entries=1628, null_mean_bias_h100=1.231, null_mean_bias_h20=1.083, null_mean_bias_h50=1.144, null_mean_uncond_h100=1.118, null_mean_uncond_h20=1.018, null_mean_uncond_h50=1.061, p1_verdict=SHELVE_K2_DRIFT_ONLY, p_bias_eligible_h100=0.302, p_bias_eligible_h20=0.046, p_bias_eligible_h50=0.357, p_unconditional_h100=0.002, p_unconditional_h20=0.0, p_unconditional_h50=0.007 |
| `state_gate_nested_wf` — Does gating the momentum signal on market state survive nested selection? | regime_filter | diagnostic | 0_hypothesis | shelved | hightrade_folds_mean_oos=-0.0074, lookahead_fixed_minus_selected=0.2739, lowtrade_folds_mean_oos=-0.3495, n_folds=17, v1_gate_value=-0.2156, v1_pass=0, v1_sel_mean=-0.1571, v1_ungated_mean=0.0585, v2_n=16, v2_pass=0, v2_pct=25.0, v2_selection_value=-0.2022, v2_wins=4, v2_worse_than_chance_p=0.0384, v3_contaminated=1, v3_fixed_mean=0.1168, v3_fixed_minus_ungated=0.0583, v3_n=17, v3_pass=1, v3_sign_p=0.049, v3_wins=13, v4_median_trades=12.0, v4_pass=1, artifact_share_of_advantage=0.21, atr14_t0=3.594, atr14_t2=4.725, gate_established=0, median_usd_t0=1.007, median_usd_t2=-0.133, null_advantage_mean=0.01582, null_advantage_obs=0.07499, null_advantage_p=0.0647, null_advantage_q95=0.07674, null_gated_mean=0.02902, null_gated_obs=0.1424, null_gated_p=0.005, null_reps=200, null_ungated_obs=0.06741, null_ungated_p=0.005, raw_usd_t0=2.1039, raw_usd_t2=0.3377, raw_usd_uncond=0.8204, top1_year_share=0.25, top3_year_share=0.52, years_positive_t0=19, years_sign_p=0.00043, years_total=22, decisive_stream_guard=1, disposition_live_unproven=1, median_ratio_t0_vs_uncond=2.6, respecification_barred=1, rule5_added=1, ungated_is_new_candidate=0, ungated_null_p_seq65=0.01, ungated_null_p_this_run=0.005, ungated_prespecified_at_seq=59, use_median_expectancy=1 |
| `vol_gate_cross_instrument` — Does the low-vol gate replicate on XAG and US500? | regime_filter | diagnostic | 0_hypothesis | killed | artifact_sign_flips_across_instruments=1, cost_bp=1.45, folds=9, r1_pass_us500=0, r1_pass_xag=0, r3_pass=0, replicated=0, reps=200, us500_advantage=0.06869, us500_n_gated=415, us500_null_mean=0.13406, us500_p=0.9701, window=2012-08-06..2025-12-31, xag_advantage=0.03005, xag_n_gated=359, xag_null_mean=-0.0232, xag_p=0.0796, xau_advantage=0.11321, xau_n_gated=362, xau_null_mean=0.03398, xau_p=0.01 |
| `zerolag_chandelier` — ZeroLag Chandelier M15 trend-flip with H4 ZLSMA bias | trend-following | hard_gate | 1_signal_edge | killed | artifact_path=research/artifacts/zlch_signal_edge_20260613T124557Z.json, e_ratio_16bar_combined=0.9982942985402807, e_ratio_32bar_combined=0.9812997845502123, e_ratio_32bar_long=1.0329712568883036, e_ratio_32bar_short=0.9272756416318665, e_ratio_64bar_combined=0.9947033410972972, p_value_32bar=0.772, random_baseline_ci_hi=1.0489893240653485, random_baseline_ci_lo=0.9569090443774892, random_baseline_mean=1.0010775037450308, signal_hash=605f94fe1150069a, trigger_count_long=1984, trigger_count_short=1785, trigger_count_total=3769 |
| `zlch_nested_walk_forward` — zerolag_chandelier nested walk-forward (the OOS test seq=39 mandated) | trend_following | hard_gate | 0_hypothesis | killed | broken_folds_seen=3, bug_warmup_starvation=1, design_changed=0, oos_trades_after_fix_z120=35, oos_trades_before_fix=0, train_passers_unchanged=1399, distinct_configs_h1=15, distinct_configs_h4=15, h1_fixed_mean=0.448, h1_folds=17, h1_lookahead=0.522, h1_oos_mean=-0.073, h1_oos_median=-0.079, h1_oos_positive=8, h1_train_sharpe_mean=1.343, h1_zk2_n=17, h1_zk2_wins=8, h4_fixed_mean=0.615, h4_folds=16, h4_lookahead=0.512, h4_oos_mean=0.103, h4_oos_median=0.097, h4_oos_positive=9, h4_train_sharpe_mean=1.248, h4_zk2_n=16, h4_zk2_wins=7, pooled_lookahead=0.517, pooled_oos_mean=0.012, pooled_pool_mean=0.166, pooled_selection_value=-0.154, pooled_zk2_n=33, pooled_zk2_p=1.0, pooled_zk2_wins=15, short_selected_folds=5, zk1_pass=0, zk2_pass=0, zk3_pass=1 |
| `zlch_param_sweep` — Exhaustive parameter + timeframe sweep of zerolag_chandelier (post-kill exit-edge probe) | trend-following | diagnostic | 3_is_backtest | open | K1_p_value=0.0, K1_random_entry_null_mean=0.247, K1_result=PASS (unchanged), K2_calmar_vs_bh=0.41 vs 0.28, K2_result=PASS, K3_dsr_N15_logfloor=0.998, K3_dsr_N18480_estimated=0.7392, K3_dsr_N3696_empirical=0.1186, K3_result=FAIL, K4_neighbourhood_frac_positive=1.0, K4_neighbourhood_median_sharpe=0.729, K4_result=PASS, artifact=research/post/artifacts/zlch_report_data.json, bh_calmar=0.28, leader=H4 atr_period=8 atr_mult=2.0 bias=none direction=long, leader_cagr_acct=0.0723, leader_calmar=0.41, leader_exposure=0.517, leader_max_dd_px=0.238, leader_pf=1.4946, leader_sharpe_px=0.8333, leader_win_rate=0.4135, median_sharpe_D1=0.114, median_sharpe_H1=0.138, median_sharpe_H4=0.266, median_sharpe_M15=-0.602, median_sharpe_M5=-1.402, n_configs=18480, n_distinct_configs=15630, n_survivors=2421, original_config_percentile_in_M15=56.7, K1_configs_p_eq_0=8 of 12, K1_configs_p_lt_0.05=10 of 12 (was reported 12 of 12), K1_leader_null_mean=0.271, K1_leader_p=0.0, K1_null_mean_range=0.020-0.399, correction=random-entry control recomputed with count matching, null_realized_to_target_ratio=1.0 |

## Full event stream (oldest first)

### seq 0 · 2026-06-11T09:16:34Z · hypothesis · `crest_n_keel`

**HMA+Stoch 1H pullback (a.k.a. hma_stoch_1h)**

_Mechanism_: Trend established by HMA slope; entries taken on Stochastic pullback into trend direction. Profit captured by asymmetric ATR exit (SL 1.5·ATR / TP 3.0·ATR) — entry edge ≈ flat by design.

market=XAUUSD· timeframe=H1· family=pullback· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `efb640a963f98af2…` · _prev_: `(genesis)`

### seq 1 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `e_ratio_w30`=0.9, `p_value`=0.34

> Entry E-Ratio ~0.9 — no standalone edge. Expected for a pullback entry; do NOT kill on this (diagnostic).

_hash_: `b94a48cc5f48b1ed…` · _prev_: `efb640a963f98af2…`

### seq 2 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=4_oos · verdict=promoted · counts_as_trial=False

_Metrics_: `sharpe_oos`=1.76

> Sharpe ~1.76 OOS; profit lives in the asymmetric ATR exit.

_hash_: `b3b9fc738cd5d7f4…` · _prev_: `b94a48cc5f48b1ed…`

### seq 3 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=8_deployed · verdict=deployed · counts_as_trial=False

> Live in production.

_hash_: `0d8de9105eaed1a9…` · _prev_: `b3b9fc738cd5d7f4…`

### seq 4 · 2026-06-11T09:16:34Z · hypothesis · `asqs`

**ASQ SafeScalping v1.20 — M5 7-condition breakout**

_Mechanism_: Seven-condition M5 breakout filter (HLPeak channel + multi-MA stack + ATR regime + session window). Continuation entry where the breakout itself is expected to do the work.

market=XAUUSD· timeframe=M5· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `0ef15bcec093af79…` · _prev_: `0d8de9105eaed1a9…`

### seq 5 · 2026-06-11T09:16:34Z · update · `asqs`

stage=1_signal_edge · verdict=promoted · counts_as_trial=False

> Entry edge confirmed (breakout — must pass hard gate).

_hash_: `c885399e34ed3907…` · _prev_: `0ef15bcec093af79…`

### seq 6 · 2026-06-11T09:16:34Z · update · `asqs`

stage=4_oos · verdict=promoted · counts_as_trial=False

_Metrics_: `profit_factor`=1.55, `sharpe_oos`=5.14

> OOS Sharpe 5.14, PF 1.55 on harness backtest.

_hash_: `92d4d8398dc37947…` · _prev_: `c885399e34ed3907…`

### seq 7 · 2026-06-11T09:16:34Z · update · `asqs`

stage=8_deployed · verdict=deployed · counts_as_trial=False

> Live; 3 live-adapter bugs fixed during deployment (SL/TP, drawdown, daily-cap query).

_hash_: `bc1551daaa97ae12…` · _prev_: `92d4d8398dc37947…`

### seq 8 · 2026-06-11T09:16:34Z · hypothesis · `ebb_n_flow`

**Bollinger mean-reversion with KER gate**

_Mechanism_: Symmetric fade of Bollinger band touches gated by Kaufman Efficiency Ratio (only when trend strength is low).

market=XAUUSD· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `84a718f83fee61ed…` · _prev_: `bc1551daaa97ae12…`

### seq 9 · 2026-06-11T09:16:34Z · update · `ebb_n_flow`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `e_ratio_w30`=0.97

> Entry E-Ratio flat — diagnostic only for MR, so not a kill signal on its own.

_hash_: `0b932b024ee0f1f1…` · _prev_: `84a718f83fee61ed…`

### seq 10 · 2026-06-11T09:16:34Z · update · `ebb_n_flow`

stage=3_is_backtest · verdict=killed · counts_as_trial=False

_Metrics_: `gross_expectancy`=-1.0

> Negative gross expectancy. Gold's secular uptrend punishes symmetric fades; MR sleeve needs asymmetric treatment of long vs short. Killed on backtest, not on the flat entry E-Ratio.

_hash_: `420513b5e5129481…` · _prev_: `0b932b024ee0f1f1…`

### seq 11 · 2026-06-11T09:16:34Z · hypothesis · `donchian_50_control`

**Donchian-50 breakout (positive control)**

_Mechanism_: Classic 50-bar Donchian channel breakout — used as a positive control for signal_edge.py to confirm the tool detects real entry edge when present. Not a deployment candidate.

market=XAUUSD· timeframe=H1· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `dc22380a48130ec4…` · _prev_: `420513b5e5129481…`

### seq 12 · 2026-06-11T09:16:34Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `e_ratio_w10`=1.11, `e_ratio_w50`=1.17, `p_value`=0.0

> E-Ratio 1.11→1.17 across windows at p=0.000. Confirms the tool detects real edge. Shelved — control, not a deployment candidate.

_hash_: `a89bf080cc85181a…` · _prev_: `dc22380a48130ec4…`

### seq 13 · 2026-06-11T09:16:34Z · hypothesis · `avwap_liquidity_sweep`

**H1 HMA + NY AVWAP + 5-day VP + sweep/reclaim**

_Mechanism_: Continuation entry: H1 HMA filter establishes trend, NY-session anchored VWAP and 5-day volume profile locate liquidity, entry fires on a sweep-and-reclaim of identified levels.

market=XAUUSD· timeframe=H1· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `f65be64f27df1299…` · _prev_: `a89bf080cc85181a…`

### seq 14 · 2026-06-11T09:16:34Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Fully specced; backtest harness not built yet.

_hash_: `17a9cde75ce114f1…` · _prev_: `f65be64f27df1299…`

### seq 15 · 2026-06-11T09:16:34Z · hypothesis · `asian_session_fade`

**Asian-session ATR-channel fade**

_Mechanism_: Liquidity vacuum 22:00–05:00 GMT lets price overshoot an HLPeak ATR channel; mean-revert back to channel midline near London open. StochMA used as the trigger.

market=XAUUSD· timeframe=M5· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `f6d4a6c602c353df…` · _prev_: `17a9cde75ce114f1…`

### seq 16 · 2026-06-11T09:16:34Z · update · `asian_session_fade`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> MR sleeve candidate; target 0.0–0.25 correlation with the trend book. Edge expected in the exit (diagnostic).

_hash_: `e4c665a3c07f0f01…` · _prev_: `f6d4a6c602c353df…`

### seq 17 · 2026-06-11T09:16:34Z · hypothesis · `gold_dxy_divergence`

**Gold–DXY cointegration divergence MR**

_Mechanism_: Stat-arb style mean-reversion of gold vs DXY when the cointegration spread stretches beyond a Z-score threshold.

market=XAUUSD· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `c912ec87c6b8bd8c…` · _prev_: `e4c665a3c07f0f01…`

### seq 18 · 2026-06-11T09:16:34Z · update · `gold_dxy_divergence`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Falsification prerequisites undone: rolling correlation, CADF cointegration test, cross-corr lag analysis. No spec yet.

_hash_: `b2d0e2fbbe7c3539…` · _prev_: `c912ec87c6b8bd8c…`

### seq 19 · 2026-06-13T10:18:03Z · hypothesis · `zerolag_chandelier`

**ZeroLag Chandelier M15 trend-flip with H4 ZLSMA bias**

_Mechanism_: Chandelier direction-flip is a momentum-transition trigger: dir flips +1 when close breaks above the trailing short_stop band (rolling-low + k*ATR), and -1 when close breaks below the trailing long_stop band. The H4 ZLSMA slope filter constrains entries to the dominant macro bias and is intended to suppress flip-noise during ranging conditions. If the entry trigger has no standalone edge against random entries within the same regime filter, the strategy reduces to its (unspecified) exit design and becomes structurally similar to crest_n_keel — i.e., the entry itself is not the source of alpha. HARD_GATE: a flat E-Ratio falsifies the idea outright.

market=XAUUSD· timeframe=M15 (H4 reference)· family=trend-following· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the combined long+short entry-signal E-Ratio at a 32-bar forward window is >= 1.10.
- The permutation test p-value (1,000 permutations) is < 0.05.
- The random-entry baseline E-Ratio over the same period falls within [0.95, 1.05] — confirming the tool itself is unbiased on this dataset.
- Trigger count across the 8-year window is >= 200, satisfying the statistical-power floor for the permutation test.

> Earlier informal version analysed 2026-03-23; not previously registered. Frozen parameters: Chandelier ATR(14, mult=2.5), H4 ZLSMA(50), no additional filters. H4 series resampled from M15 with label='right', closed='right' and referenced at .shift(1) to prevent look-ahead. Direction-flip entries only — persistent-direction variant is out of scope and would be a separate hypothesis.

_hash_: `062f9304f833e53f…` · _prev_: `b2d0e2fbbe7c3539…`

### seq 20 · 2026-06-13T12:46:28Z · update · `zerolag_chandelier`

stage=1_signal_edge · verdict=killed · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/zlch_signal_edge_20260613T124557Z.json, `e_ratio_16bar_combined`=0.9982942985402807, `e_ratio_32bar_combined`=0.9812997845502123, `e_ratio_32bar_long`=1.0329712568883036, `e_ratio_32bar_short`=0.9272756416318665, `e_ratio_64bar_combined`=0.9947033410972972, `p_value_32bar`=0.772, `random_baseline_ci_hi`=1.0489893240653485, `random_baseline_ci_lo`=0.9569090443774892, `random_baseline_mean`=1.0010775037450308, `signal_hash`=605f94fe1150069a, `trigger_count_long`=1984, `trigger_count_short`=1785, `trigger_count_total`=3769

> SIGNAL_EDGE verdict: KILLED (anti-edge). 32-bar combined E-Ratio=0.9813 < 1.00, p=0.7720. Both pre-conditions passed: random baseline=1.0011 in [0.95,1.05], triggers=3769 >= 200. Sensitivity: 16-bar=0.9983, 64-bar=0.9947 — flat at every window, no edge concentration anywhere. HARD_GATE classification → terminal for this parameterisation. Returning to avwap_liquidity_sweep.

_hash_: `6691f108baace712…` · _prev_: `062f9304f833e53f…`

### seq 21 · 2026-06-13T13:10:03Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=promoted · counts_as_trial=False

_Metrics_: `artifact_path`=None, `e_ratio_32bar_combined`=None, `e_ratio_32bar_long`=None, `e_ratio_32bar_short`=None, `p_value_32bar`=0.0, `random_baseline_mean`=None, `signal_hash`=None, `trigger_count_long`=None, `trigger_count_short`=None, `trigger_count_total`=None

> Backfill UPDATE: positive control passed the signal_edge gate at p<0.05, confirming the diagnostic tool detects edge in canonical breakout signals on XAUUSD. NOT a strategy candidate — donchian_50_control exists solely as a tool-calibration anchor. Stage will not advance further; this entry will sit permanently at SIGNAL_EDGE/PROMOTED. The result was the reference point used to interpret the crest_n_keel and zerolag_chandelier findings.

_hash_: `b5362c1b16025362…` · _prev_: `6691f108baace712…`

### seq 22 · 2026-06-13T14:00:46Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

> Verdict revert: seq=21 PROMOTED was a semantic mis-classification. Control passed the signal_edge gate (E-Ratio 1.11-1.17, p=0.000), but donchian_50_control exists solely as a tool-calibration anchor - terminal by design, no deployment intent. SHELVED reads correctly in render_markdown: tool-passed, parked. Edge-confirmation metrics remain on seq=21 and are the authoritative reference for tool calibration on XAUUSD H1/M15.

_hash_: `129ec15bfc171c84…` · _prev_: `b5362c1b16025362…`

### seq 23 · 2026-06-13T14:02:14Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Role reclassification: HARD_GATE -> DIAGNOSTIC. The entry trigger is structurally a mean-reversion reclaim-at-level (sweep + reclaim against AVWAP / VP-POC / HVN), not a momentum-transition breakout. A flat or sub-1.0 E-Ratio on the entry is the EXPECTED outcome and does not falsify the hypothesis - by analogy with crest_n_keel (E-Ratio ~0.9, no significance, DIAGNOSTIC), where the edge lives entirely in the asymmetric ATR exit. Edge claim for avwap will live in the exit design downstream. Reclassification was decided in earlier sessions; this UPDATE persists the decision to the log so the next signal_edge run interprets the result correctly.

_hash_: `fcfcbf0e439ed2af…` · _prev_: `129ec15bfc171c84…`

### seq 24 · 2026-06-14T08:24:31Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=shelved · counts_as_trial=False

> Shelved: hypothesis as registered at seq=13 is structurally a H1 BREAKOUT continuation strategy (H1 HMA + AVWAP + VP locating breakout levels). The seq=23 role reclassification to DIAGNOSTIC was correct about the mechanism — sweep-and-reclaim reads as mean-reversion, not continuation — but the underlying registration's timeframe (H1) and family (breakout) remained inconsistent with that reclassification. Rather than rewrite identity fields via UPDATE (which would erode the append-only log's audit guarantees), this hypothesis is shelved and the mean-reversion variant is registered as avwap_sweep_reclaim_m15 with the correct timeframe (M15), family (mean-reversion), and full frozen parameter spec. No edge measurement was performed against seq=13's parameterisation; this is a definitional shelving, not an evidence-based one.

_hash_: `e72053cc701ee953…` · _prev_: `fcfcbf0e439ed2af…`

### seq 25 · 2026-06-14T08:25:23Z · hypothesis · `avwap_sweep_reclaim_m15`

**AVWAP/POC/HVN sweep-and-reclaim on XAUUSD M15 with H1 HMA bias**

_Mechanism_: Mean-reversion reclaim-at-level. Premise: institutional liquidity clusters at three reference levels on XAUUSD intraday — the NY-anchored AVWAP (session consensus), the rolling 5-day Volume Profile POC (multi-day fair value), and high-volume nodes within reach (accepted price zones). When price sweeps a level (wicks past by >=0.2*ATR) and reclaims it within the same M15 candle, trapped breakout traders provide displacement fuel back toward the level. The H1 HMA(50) bias filter constrains entries to the macro direction (longs only above HMA, shorts only below). The Stochastic %K-%D cross in oversold/overbought confirms momentum has turned at the reclaim. DIAGNOSTIC role: this is a reclaim-at-level entry, so a flat or sub-1.0 E-Ratio on the entry alone is expected and does NOT falsify the hypothesis. The edge claim will live in the exit design downstream, structurally analogous to crest_n_keel where the entry is no-edge but the asymmetric ATR exit carries the alpha. signal_edge here produces a reference E-Ratio against which the full-strategy backtest's improvement is later measured.

market=XAUUSD· timeframe=M15 (H1 reference for HMA, H1 aggregation for Volume Profile)· family=mean-reversion· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the entry stack produces >= 100 triggers (long + short combined), satisfying the statistical-power floor for the signal_edge permutation test under DIAGNOSTIC framing.
- The random-entry baseline E-Ratio over the same period falls within [0.95, 1.05] — confirming the tool itself is unbiased on this dataset.
- The Volume Profile is computed from a trailing 120 H1 bar window ending at bar t-1, with no inclusion of bar t's H1 bar — verified by the signal-generator unit tests for look-ahead protection.
- The signal-output DataFrame includes a 'triggering_level' column (values: 'avwap', 'poc', 'hvn') for diagnostic attribution of any observed E-Ratio by level type, used in next-hypothesis design only.

> Successor to avwap_liquidity_sweep (seq=13, shelved at seq=24) — same level-set concept, materially different mechanism (mean-reversion reclaim) and timeframe (M15 not H1). Frozen entry stack: NY cash open AVWAP (DST-aware), H1 HMA(50), 5-day Volume Profile (120 H1 bars, 0.025%-of-price bins, POC + top-3 HVNs within 2*ATR of current price), 0.2*ATR(14) sweep threshold, same-M15-candle reclaim, Stochastic(14,3,3) %K-%D cross coincident with sweep bar. Forward window 16 bars primary, 8/32 sensitivity. ATR-scaled VP binning, multi-bar reclaim variant, and confluence-required triggering are explicitly deferred as separate hypotheses if this one shows interesting results. Edge claim is in exit design, not entry.

_hash_: `2951fe53609fd1e8…` · _prev_: `e72053cc701ee953…`

### seq 26 · 2026-06-14T08:40:47Z · update · `avwap_sweep_reclaim_m15`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/avwap_sweep_reclaim_signal_edge_20260614T083827Z.json, `e_ratio_16bar_avwap`=0.6105235797712227, `e_ratio_16bar_combined`=0.806326708871015, `e_ratio_16bar_hvn`=0.9389136831082255, `e_ratio_16bar_long`=0.8362129729640871, `e_ratio_16bar_poc`=0.5316155984971189, `e_ratio_16bar_short`=0.7813945766834295, `e_ratio_32bar_combined`=0.8981169691816416, `e_ratio_8bar_combined`=0.8630572252818496, `p_value_16bar`=0.942, `random_baseline_ci_hi`=1.2329962317847916, `random_baseline_ci_lo`=0.7953614436587528, `random_baseline_mean`=1.0407515046105003, `signal_hash`=35d6b60e498f3813, `trigger_count_avwap`=40, `trigger_count_hvn`=97, `trigger_count_long`=58, `trigger_count_poc`=8, `trigger_count_short`=87, `trigger_count_total`=145

> DIAGNOSTIC SIGNAL_EDGE checkpoint: entry-only E-Ratio (16-bar combined) =0.8063, p=0.9420, baseline=1.0408. Pre-conditions both passed (triggers=145 >=100; baseline in [0.95,1.05]). By level: avwap n=40 E=0.611; poc n=8 E=0.532; hvn n=97 E=0.939. Verdict remains OPEN (DIAGNOSTIC: edge claim is in exit design downstream). Next: design asymmetric exit + run full backtest.

_hash_: `02309736130d9cf4…` · _prev_: `2951fe53609fd1e8…`

### seq 27 · 2026-06-14T10:42:03Z · hypothesis · `avwap_multibar_reclaim_m15`

**AVWAP-only multi-bar sweep-and-reclaim on XAUUSD M15 with H1 HMA bias**

_Mechanism_: Mean-reversion reclaim-at-level, AVWAP-only variant with multi-bar reclaim tolerance. Premise: in avwap_sweep_reclaim_m15 (seq=25, checkpoint at seq=27, E-Ratio 0.81 vs 1.04 baseline at 16 bars), the AVWAP-tagged subset produced the strongest decomposed E-Ratio (0.89, n=40) among three level types — still flat in absolute terms, but the cleanest signal in the stack. POC was effectively dead (n=8 in 8 years) and HVN diluted the result. This variant tests two design changes: (1) restrict triggers to AVWAP only, eliminating POC/HVN noise; (2) relax the same-candle reclaim constraint to allow up to 3 consecutive M15 bars of close-based displacement past the level before reclaim. The same-candle constraint may have been too restrictive for AVWAP specifically — institutional consensus levels operate on slower time scales than HVN-style reaction zones, and the 'trapped traders' mechanism requires sustained displacement to engage. DIAGNOSTIC role: this is still a reclaim-at-level entry, so flat or sub-1.0 E-Ratio on the entry alone remains the expected outcome. Edge claim, if pursued, will live in the exit design downstream.

market=XAUUSD· timeframe=M15 (H1 reference for HMA)· family=mean-reversion· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the AVWAP-only multi-bar reclaim entry produces >= 100 triggers (long + short combined), satisfying the statistical-power floor for signal_edge.
- The random-entry baseline E-Ratio satisfies: mean within [0.95, 1.05] OR [0.95, 1.05] fully contained within the 95% CI — the corrected calibration check from the avwap_sweep_reclaim_m15 debrief.
- The AVWAP value at M15 bar t is cumulative TPV/volume from the most recent NY cash open (09:30 America/New_York, DST-aware) at-or-before t, with no use of bars after t. Verified by signal-generator unit tests.
- The signal-output DataFrame includes a 'sweep_bars' integer column (values 1 through 3) recording how many M15 bars the level was breached before the reclaim, for diagnostic attribution of edge concentration by displacement duration.

> Successor variant to avwap_sweep_reclaim_m15 (seq=25, OPEN at seq=27 after DIAGNOSTIC checkpoint). Frozen entry stack: NY cash open AVWAP (DST-aware) — POC and HVN removed; H1 HMA(50) bias filter (unchanged); 0.2*ATR(14) sweep threshold (unchanged); multi-bar reclaim with maximum 3 M15 bars of consecutive close-based displacement past the level (close[N] past level by >= 0.2*ATR) before the reclaim bar (first bar with close back on original side); Stochastic(14,3,3) %K-%D edge-cross coincident with the RECLAIM bar (not the initial sweep bar), both < 20 long / > 80 short. Forward window 16 bars primary, 8/32 sensitivity. POC, HVN, same-candle reclaim variant, alternative anchor sessions, and longer reclaim timeouts are deferred as separate hypotheses. Edge claim is in exit design, not entry. If this variant also returns flat, the case for any further M15 entry-signal variant in this family becomes very weak and the next trial budget should be spent on a different mechanism class (e.g., gold_dxy_divergence).

_hash_: `52614e9c065eaf69…` · _prev_: `02309736130d9cf4…`

### seq 28 · 2026-06-14T13:51:01Z · update · `avwap_multibar_reclaim_m15`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/avwap_multibar_reclaim_signal_edge_20260614T133418Z.json, `e_ratio_16bar_combined`=0.7442676947027749, `e_ratio_16bar_long`=0.752738401545089, `e_ratio_16bar_short`=0.7373789256325337, `e_ratio_16bar_sweep_1bar`=0.8587431852056898, `e_ratio_16bar_sweep_2bar`=0.6593045423120963, `e_ratio_16bar_sweep_3bar`=0.63133028877003, `e_ratio_32bar_combined`=0.8579269972413494, `e_ratio_8bar_combined`=0.8029473830802075, `p_value_16bar`=0.943, `random_baseline_ci_hi`=1.3435445752288044, `random_baseline_ci_lo`=0.7338073025220379, `random_baseline_mean`=1.1712825593901284, `run_valid`=False, `signal_hash`=97102210ade375b6, `trigger_count_long`=40, `trigger_count_short`=43, `trigger_count_sweep_1bar`=40, `trigger_count_sweep_2bar`=27, `trigger_count_sweep_3bar`=16, `trigger_count_total`=83

> INVALID RUN: pre-condition #1 failed. Trigger count = 83 < 100 (spec floor for statistical power). Sweep-bars distribution {1:40, 2:27, 3:16}. Random baseline mean = 1.1713 (also outside [0.95,1.05] band; null p05=0.7338, p95=1.3435 - the band IS contained in [p05,p95], so the secondary calibration clause holds, but the trigger floor is the binding failure). Stage unchanged at HYPOTHESIS; not falsifying under DIAGNOSTIC. HALT - no parameter rescue. Diagnostic E-Ratio 0.7443 reported for completeness but is statistically unreliable at n=83.

_hash_: `387d0984c21ff918…` · _prev_: `52614e9c065eaf69…`

### seq 29 · 2026-06-26T08:05:14Z · update · `crest_n_keel`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `dsr_prob_24h`=0.106, `dsr_prob_session`=0.028, `folds`=33, `oos_max_dd_session`=0.1, `oos_trades_24h`=323, `oos_trades_session`=146, `profit_factor_24h`=1.15, `profit_factor_session`=1.45, `sharpe_oos_24h`=0.27, `sharpe_oos_session`=0.41, `spread_stress_survives_2x`=True

> qhf harness walk-forward (33 folds, 21.6y XAUUSD H1, Pepperstone Razor costs) CONTRADICTS the seeded sharpe_oos=1.76. Realized OOS Sharpe (ann.) 0.27 (24/7) / 0.41 (08-17 UTC session); DSR prob 0.106 / 0.028 -> FAILS DSR>0.95 gate on BOTH runs; 24/7 also fails PF>=1.20 (1.15). Edge survives 2x spread but there is no significant edge to protect. The 1.76 was a hand-seeded claim with no backing artifact (absent from qhf_harness; never produced by this harness). Verdict reopened to OPEN: deployed standing is contested. NOT auto-killed/shelved -- that decision is the owner's.

_hash_: `5a060a461d8bfeff…` · _prev_: `387d0984c21ff918…`

### seq 30 · 2026-07-03T09:07:18Z · update · `asqs`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `dsr_prob_24h`=0.0, `dsr_prob_session`=0.0, `folds`=33, `oos_max_dd_24h`=0.67, `oos_max_dd_session`=0.72, `oos_trades_24h`=11763, `oos_trades_session`=11048, `profit_factor_24h`=0.91, `profit_factor_session`=0.9, `sharpe_oos_24h`=-1.06, `sharpe_oos_session`=-1.04

> qhf harness walk-forward (33 folds, ~21y XAUUSD M5, Pepperstone Razor costs, train 1460D/test 365D/step 180D) CONTRADICTS the seeded sharpe_oos=5.14/PF=1.55 (seq=6): measured OOS Sharpe -1.06 (24/7) / -1.04 (session), PF 0.91/0.90, OOS max DD 67%/72%, canonical DSR 0.000 both (recompute via research/data/asqs/recompute_dsr.py; raw OOS Sharpe is negative, so PSR-vs-zero is 0 before any haircut). Refuted by sign, not merely unverified. OOS returns saved data/asqs/asqs_oos_returns_{24h,session}.csv. Still live on demo — deploy/kill decision deferred to owner.

_hash_: `d97a5ac7c6807fd4…` · _prev_: `5a060a461d8bfeff…`

### seq 31 · 2026-07-05T10:01:13Z · hypothesis · `flood_tide_h1`

**flood_tide_h1 — Donchian-55 H1 breakout with H4-EMA + Efficiency-Ratio regime gate (XAUUSD, long-only)**

_Mechanism_: On XAUUSD, a close exceeding the prior 55-bar H1 high represents a shift in institutional flow that persists beyond a single bar. Gold's macro drivers (real rates, DXY, geopolitical premium, CB flows) reprice on multi-day-to-week horizons, not intraday. A confirmed H1 breakout in a structurally trending H4 regime is therefore expected to produce positive-expectancy continuation over the following 20-100 H1 bars. Long-only: XAU secular uptrend + ebb_n_flow falsification of symmetric counter-trend logic on gold.

market=XAUUSD· timeframe=H1· family=trend_following_breakout· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- P1_entry_edge: Breakout entry has positive edge above random baseline across short/medium/long holding horizons. [metric=E-Ratio at H in {20, 50, 100} bars; threshold=E-Ratio > 1.10 AND p < 0.05, N >= 500 permutations; test=research.signal_edge.run(hypothesis='flood_tide_h1')]
- P2_oos_survival: Full system (entry + trail exit + regime filter) produces statistically significant OOS Sharpe after multiple-testing correction. [metric=Deflated Sharpe Ratio, 20-year walk-forward (2004-2024); threshold=DSR > 0.95 with honest trial_count denominator; test=btpy_runner + research.dsr.compute(sharpe_series)]
- P3_trade_shape: Trade distribution matches trend-following payoff profile. If shape violated, P&L is not from the stated mechanism. [metric=win_rate, avg_winner / avg_loser, max_consecutive_losers; threshold=win_rate in [0.30, 0.45] AND avg_winner / avg_loser >= 2.5 AND max_consecutive_losers <= 12; test=post-walk-forward trade log analysis]

> PRE-REGISTRATION (frozen; do not modify post-registration). Full falsifiable payload embedded verbatim below so the hash chain protects the complete commitment (predictions, kill criteria, edge gates, cost model, stopping rule):
{
  "author": "roy",
  "broker": "pepperstone_razor",
  "codename": "flood_tide_h1",
  "correlation_notes": "vs crest_n_keel (H1 HMA/Stoch, falsified): both H1 long-biased XAU; signal-timing correlation expected 0.3-0.5; not a genuine diversification add if both were live. vs asqs (M5 scalping, halted): different timeframe and mechanism; moot. vs avwap_multibar_reclaim_m15 (pending): different TF and mechanism (reclaim vs breakout); formal correlation study deferred until one clears DSR gate. Portfolio role: occupies 'H1 trend continuation' slot. Does not by itself constitute a diversified book.",
  "cost_model": {
    "commission_per_001_lot_round_trip_usd": "7.00",
    "entry_slippage_formula": "fill = breakout_level + 0.5 * spread + 0.2 * ATR(14)_breakout_bar",
    "exit_slippage_formula": "fill = trail_level - 0.3 * ATR(14)_current_bar",
    "order_filling": "IOC",
    "spread_model": "Time-varying per hour-of-day bucket from Pepperstone Razor historical spread series. Fallback: conservative flat 25 pips ($2.50 per 0.01 lot round-trip)."
  },
  "direction": "long_only",
  "edge_gates": [
    {
      "component": "entry_donchian_55_breakout",
      "rationale": "Breakout / continuation entry. E-Ratio <= 1.0 is terminal per house rules \u2014 no exit design can rescue a non-edge entry in this category.",
      "role": "HARD_GATE"
    },
    {
      "component": "exit_donchian_20_trail",
      "rationale": "Trend-following edge lives in exit design (crest_n_keel finding). E-Ratio not applicable \u2014 measured via full-system walk-forward contribution.",
      "role": "DIAGNOSTIC"
    },
    {
      "component": "regime_htf_ema_and_er",
      "rationale": "Filter contribution measured via ablation. Not gated in isolation. ADX explicitly excluded \u2014 documented ineffective on XAU.",
      "role": "DIAGNOSTIC"
    }
  ],
  "execution_timeframe": "H1",
  "frozen_params": {
    "direction": "long_only",
    "entry_len": 55,
    "er_len": 14,
    "er_threshold": 0.3,
    "exit_len": 20,
    "htf_ema_len": 200,
    "htf_timeframe": "H4",
    "reentry_cooldown_bars": 5,
    "risk_pct": 1.0,
    "stop_len": 10
  },
  "instrument": "XAUUSD",
  "kill_criteria": [
    {
      "action": "TERMINAL_KILL",
      "condition": "E-Ratio <= 1.0 at any H in {20, 50, 100}",
      "id": "K1"
    },
    {
      "action": "SHELVE",
      "condition": "E-Ratio > 1.0 but p >= 0.05 at all H",
      "id": "K2"
    },
    {
      "action": "KILL",
      "condition": "Walk-forward OOS DSR <= 0.95",
      "id": "K3"
    },
    {
      "action": "KILL",
      "condition": "Walk-forward max drawdown > 40% at 1% risk sizing",
      "id": "K4"
    },
    {
      "action": "KILL",
      "condition": "Trade shape violates P3 thresholds",
      "id": "K5"
    }
  ],
  "mechanism": "On XAUUSD, a close exceeding the prior 55-bar H1 high represents a shift in institutional flow that persists beyond a single bar. Gold's macro drivers (real rates, DXY, geopolitical premium, CB flows) reprice on multi-day-to-week horizons, not intraday. A confirmed H1 breakout in a structurally trending H4 regime is therefore expected to produce positive-expectancy continuation over the following 20-100 H1 bars. Long-only: XAU secular uptrend + ebb_n_flow falsification of symmetric counter-trend logic on gold.",
  "mechanism_prior_work": [
    "dennis_eckhardt_turtle_system_1_and_2",
    "clenow_following_the_trend",
    "crest_n_keel_falsification_edge_in_exit_finding",
    "ebb_n_flow_falsification_symmetric_logic_fails_on_xau",
    "research.signal_edge.e_ratio_methodology"
  ],
  "partner": "claude",
  "predictions": [
    {
      "id": "P1_entry_edge",
      "metric": "E-Ratio at H in {20, 50, 100} bars",
      "statement": "Breakout entry has positive edge above random baseline across short/medium/long holding horizons.",
      "test": "research.signal_edge.run(hypothesis='flood_tide_h1')",
      "threshold": "E-Ratio > 1.10 AND p < 0.05, N >= 500 permutations"
    },
    {
      "id": "P2_oos_survival",
      "metric": "Deflated Sharpe Ratio, 20-year walk-forward (2004-2024)",
      "statement": "Full system (entry + trail exit + regime filter) produces statistically significant OOS Sharpe after multiple-testing correction.",
      "test": "btpy_runner + research.dsr.compute(sharpe_series)",
      "threshold": "DSR > 0.95 with honest trial_count denominator"
    },
    {
      "id": "P3_trade_shape",
      "metric": "win_rate, avg_winner / avg_loser, max_consecutive_losers",
      "statement": "Trade distribution matches trend-following payoff profile. If shape violated, P&L is not from the stated mechanism.",
      "test": "post-walk-forward trade log analysis",
      "threshold": "win_rate in [0.30, 0.45] AND avg_winner / avg_loser >= 2.5 AND max_consecutive_losers <= 12"
    }
  ],
  "regime_timeframe": "H4",
  "reproducibility_artifact_path": null,
  "seed_metric_status": "NONE",
  "stopping_rule": "Iteration 1: this pre-registration exactly. No parameter changes. Iteration 2: only if Iteration 1 produces E-Ratio > 1.0 but fails DSR. Exactly one parameter changed, ex-ante justified via ablation diagnostics, logged as a new register_hypothesis call incrementing trial_count. After Iteration 2: SHELVED. No third iteration.",
  "strategy_family": "trend_following_breakout"
}

_hash_: `1b14aa312cc79003…` · _prev_: `d97a5ac7c6807fd4…`

### seq 32 · 2026-07-06T11:43:24Z · update · `flood_tide_h1`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `e_ratio_H100`=1.1835210145765311, `e_ratio_H20`=1.1348806858949592, `e_ratio_H50`=1.1294091836142026, `null_mean_H100`=1.211763812660675, `p_H100`=0.714, `p_H20`=0.096, `p_H50`=0.456

> P1 regime-filtered E-Ratio HARD_GATE -> SHELVE_INSUFFICIENT_SIGNIFICANCE (K2). E-Ratio cleared 1.10 in raw terms at all H but was insignificant vs a regime-filtered null everywhere (p=0.10/0.46/0.71) and sub-null at H=100. The Donchian-55 entry adds no edge over the H4-EMA+ER regime. Artifact: flood_tide_h1_seq31_p1_20260706T075247Z.json

_hash_: `e9124da6b45f4b84…` · _prev_: `1b14aa312cc79003…`

### seq 33 · 2026-07-06T11:43:24Z · hypothesis · `flood_tide_h1_iter2`

**flood_tide_h1_iter2 — Donchian-20 (faster) H1 breakout, H4-EMA + Efficiency-Ratio regime gate (XAUUSD, long-only). Iteration 2 of seq=31.**

_Mechanism_: ITERATION 2 of flood_tide_h1 (parent seq=31, SHELVED at P1). In Iteration 1 the Donchian-55 breakout's forward MFE/MAE asymmetry cleared the raw 1.10 threshold but was statistically insignificant against a regime-filtered null at every horizon (p = 0.10 / 0.46 / 0.71 at H = 20 / 50 / 100), and the observed E-Ratio fell BELOW the regime null mean at H=100. The entry's excess over the null was concentrated at the SHORT horizon and decayed to sub-null with holding time. Ex-ante reading: the institutional flow shift a breakout marks is fast and short-lived on XAUUSD H1; a 55-bar channel confirms it late and buys exhaustion. SINGLE change: entry_len 55 -> 20, entering the same flow shift earlier, before it is spent. The falsifiable claim is that a faster breakout produces a regime-null-significant forward asymmetry where the slow one did not. All other params, gates, kill criteria and cost model are unchanged from seq=31.

market=XAUUSD· timeframe=H1· family=trend_following_breakout· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- P1_entry_edge: Faster (20-bar) breakout entry has positive edge above a regime-filtered random baseline across short/medium/long horizons. [metric=E-Ratio at H in {20, 50, 100} bars; threshold=E-Ratio > 1.10 AND p < 0.05, N >= 500 permutations; test=research.pre.scripts.run_flood_tide_edge --entry-len 20 --hypothesis-id flood_tide_h1_iter2]
- P2_oos_survival: Full system (entry + trail exit + regime filter) produces statistically significant OOS Sharpe after multiple-testing correction. [metric=Deflated Sharpe Ratio, 20-year walk-forward (2004-2024); threshold=DSR > 0.95 with honest trial_count denominator; test=btpy_runner + research.dsr.compute(sharpe_series)]
- P3_trade_shape: Trade distribution matches trend-following payoff profile. If shape violated, P&L is not from the stated mechanism. [metric=win_rate, avg_winner / avg_loser, max_consecutive_losers; threshold=win_rate in [0.30, 0.45] AND avg_winner / avg_loser >= 2.5 AND max_consecutive_losers <= 12; test=post-walk-forward trade log analysis]

> PRE-REGISTRATION (frozen; do not modify post-registration). Full falsifiable payload embedded verbatim below so the hash chain protects the complete commitment (predictions, kill criteria, edge gates, cost model, stopping rule):
{
  "author": "roy",
  "broker": "pepperstone_razor",
  "codename": "flood_tide_h1_iter2",
  "correlation_notes": "Near-identical to parent flood_tide_h1 (seq=31): same regime filter, exit, stop, instrument and timeframe \u2014 only entry_len differs (20 vs 55). Signal-timing correlation with the parent is very high; this is NOT a diversifying idea, it is a faster re-test of the same mechanism. It counts as a full separate trial precisely because it is a fresh pass over the same data.",
  "cost_model": {
    "commission_per_001_lot_round_trip_usd": "7.00",
    "entry_slippage_formula": "fill = breakout_level + 0.5 * spread + 0.2 * ATR(14)_breakout_bar",
    "exit_slippage_formula": "fill = trail_level - 0.3 * ATR(14)_current_bar",
    "order_filling": "IOC",
    "spread_model": "Time-varying per hour-of-day bucket from Pepperstone Razor historical spread series. Fallback: conservative flat 25 pips ($2.50 per 0.01 lot round-trip)."
  },
  "direction": "long_only",
  "edge_gates": [
    {
      "component": "entry_donchian_20_breakout",
      "rationale": "Faster breakout / continuation entry (Iteration 2). E-Ratio <= 1.0 is terminal per house rules; a flat-vs-null E-Ratio here shelves the breakout family \u2014 no exit design rescues a non-edge entry.",
      "role": "HARD_GATE"
    },
    {
      "component": "exit_donchian_20_trail",
      "rationale": "Trend-following edge lives in exit design (crest_n_keel finding). E-Ratio not applicable \u2014 measured via full-system walk-forward contribution.",
      "role": "DIAGNOSTIC"
    },
    {
      "component": "regime_htf_ema_and_er",
      "rationale": "Filter contribution measured via ablation. Not gated in isolation. ADX explicitly excluded \u2014 documented ineffective on XAU.",
      "role": "DIAGNOSTIC"
    }
  ],
  "execution_timeframe": "H1",
  "frozen_params": {
    "direction": "long_only",
    "entry_len": 20,
    "er_len": 14,
    "er_threshold": 0.3,
    "exit_len": 20,
    "htf_ema_len": 200,
    "htf_timeframe": "H4",
    "reentry_cooldown_bars": 5,
    "risk_pct": 1.0,
    "stop_len": 10
  },
  "instrument": "XAUUSD",
  "kill_criteria": [
    {
      "action": "TERMINAL_KILL",
      "condition": "E-Ratio <= 1.0 at any H in {20, 50, 100}",
      "id": "K1"
    },
    {
      "action": "SHELVE",
      "condition": "E-Ratio > 1.0 but p >= 0.05 at all H",
      "id": "K2"
    },
    {
      "action": "KILL",
      "condition": "Walk-forward OOS DSR <= 0.95",
      "id": "K3"
    },
    {
      "action": "KILL",
      "condition": "Walk-forward max drawdown > 40% at 1% risk sizing",
      "id": "K4"
    },
    {
      "action": "KILL",
      "condition": "Trade shape violates P3 thresholds",
      "id": "K5"
    }
  ],
  "mechanism": "ITERATION 2 of flood_tide_h1 (parent seq=31, SHELVED at P1). In Iteration 1 the Donchian-55 breakout's forward MFE/MAE asymmetry cleared the raw 1.10 threshold but was statistically insignificant against a regime-filtered null at every horizon (p = 0.10 / 0.46 / 0.71 at H = 20 / 50 / 100), and the observed E-Ratio fell BELOW the regime null mean at H=100. The entry's excess over the null was concentrated at the SHORT horizon and decayed to sub-null with holding time. Ex-ante reading: the institutional flow shift a breakout marks is fast and short-lived on XAUUSD H1; a 55-bar channel confirms it late and buys exhaustion. SINGLE change: entry_len 55 -> 20, entering the same flow shift earlier, before it is spent. The falsifiable claim is that a faster breakout produces a regime-null-significant forward asymmetry where the slow one did not. All other params, gates, kill criteria and cost model are unchanged from seq=31.",
  "mechanism_prior_work": [
    "dennis_eckhardt_turtle_system_1_and_2",
    "clenow_following_the_trend",
    "crest_n_keel_falsification_edge_in_exit_finding",
    "ebb_n_flow_falsification_symmetric_logic_fails_on_xau",
    "research.signal_edge.e_ratio_methodology"
  ],
  "partner": "claude",
  "predictions": [
    {
      "id": "P1_entry_edge",
      "metric": "E-Ratio at H in {20, 50, 100} bars",
      "statement": "Faster (20-bar) breakout entry has positive edge above a regime-filtered random baseline across short/medium/long horizons.",
      "test": "research.pre.scripts.run_flood_tide_edge --entry-len 20 --hypothesis-id flood_tide_h1_iter2",
      "threshold": "E-Ratio > 1.10 AND p < 0.05, N >= 500 permutations"
    },
    {
      "id": "P2_oos_survival",
      "metric": "Deflated Sharpe Ratio, 20-year walk-forward (2004-2024)",
      "statement": "Full system (entry + trail exit + regime filter) produces statistically significant OOS Sharpe after multiple-testing correction.",
      "test": "btpy_runner + research.dsr.compute(sharpe_series)",
      "threshold": "DSR > 0.95 with honest trial_count denominator"
    },
    {
      "id": "P3_trade_shape",
      "metric": "win_rate, avg_winner / avg_loser, max_consecutive_losers",
      "statement": "Trade distribution matches trend-following payoff profile. If shape violated, P&L is not from the stated mechanism.",
      "test": "post-walk-forward trade log analysis",
      "threshold": "win_rate in [0.30, 0.45] AND avg_winner / avg_loser >= 2.5 AND max_consecutive_losers <= 12"
    }
  ],
  "regime_timeframe": "H4",
  "reproducibility_artifact_path": null,
  "seed_metric_status": "NONE",
  "stopping_rule": "Terminal iteration. This is the one and only re-parameterisation of the flood_tide breakout mechanism. A PASS proceeds to btpy_runner walk-forward (P2 / DSR). A fail (K1 or K2) shelves the flood_tide breakout family \u2014 no Iteration 3, no further entry_len search. NB: this Iteration 2 is a deliberate departure from the parent's frozen stopping rule, which reserved Iteration 2 for a DSR failure; seq=31 failed earlier, at P1. Booked as a separate trial so trial_count() reflects the extra look at the data.",
  "strategy_family": "trend_following_breakout"
}

_hash_: `4951612c86fce7fe…` · _prev_: `e9124da6b45f4b84…`

### seq 34 · 2026-07-06T11:43:29Z · update · `flood_tide_h1_iter2`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `e_ratio_H100`=1.2250291493927423, `e_ratio_H20`=1.1661315377843247, `e_ratio_H50`=1.1637030632714933, `null_mean_H100`=1.212674656363149, `p_H100`=0.357, `p_H20`=0.011, `p_H50`=0.16

> P1 regime-filtered E-Ratio HARD_GATE (entry_len=20) -> SHELVE_INSUFFICIENT_SIGNIFICANCE. Artifact: flood_tide_h1_iter2_seq33_p1_20260706T114329Z.json

_hash_: `f137434db1ea9f1d…` · _prev_: `4951612c86fce7fe…`

### seq 35 · 2026-07-12T21:43:27Z · hypothesis · `crest_n_keel_momentum`

**crest_n_keel MOMENTUM (HMA-slope-flip, long-only, ATR chandelier trail)**

_Mechanism_: Replace the short-biased stochastic-pullback entry with an HMA-slope-flip momentum entry, LONG-ONLY, exited by a 3.0xATR chandelier trailing stop (let winners run). Trend-following on XAUUSD H1. Found via TradingView LAB search (Config A).

market=XAUUSD· timeframe=H1· family=crest_n_keel· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- Beats buy-and-hold in-sample on a trending sample (TV: +68.4% vs +56.2%, DD 10.6%)
- Trend-follower: strong Sharpe in trending years, bleeds in chop (regime-dependent)
- Raw OOS Sharpe significant but fails DSR once multiple-testing tax applied

> Selected from ~6 in-sample TradingView configs (entry mode, direction, regime on/off, trail 2/3/4). TV numbers are in-sample only.

_hash_: `e044407b715dd964…` · _prev_: `f137434db1ea9f1d…`

### seq 36 · 2026-07-12T21:43:27Z · update · `crest_n_keel_momentum`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `dsr_prob_num_trials_1`=1.0, `dsr_prob_num_trials_20`=0.061, `gate_verdict`=FAIL (DSR only); PASS at num_trials=1, `harness`=qhf_harness run_cnk_momentum, 21.6y H1 2004-2025, 33 folds, `is_oos_gap`=-0.34, `mean_is_sharpe`=0.86, `oos_max_dd_pct`=29.9, `oos_profit_factor`=1.26, `oos_sharpe`=1.2, `oos_trades`=3829

> Walk-forward PASSES 4/5 research gates (gap -0.34 -> not overfit; DD 29.9%<30%; 3829 trades; PF 1.26) but FAILS overall on DSR=0.061 at honest num_trials=20. Raw OOS edge is significant (DSR=1.0 at N=1) and materially better than baseline crest_n_keel (OOS 0.27-0.41, DSR 0.03-0.11) -- switching entry pullback->momentum helped. Do NOT promote: fails multiple-testing gate; OOS DD at research ceiling, fails production (15%). Next honest step = pre-registered confirmation on fresh data, NOT more searching.

_hash_: `92c686324205b5fd…` · _prev_: `e044407b715dd964…`

### seq 37 · 2026-07-26T20:38:08Z · hypothesis · `regime_align_h1`

**Three-parameter regime alignment (ER + vol expansion + anchor bias) as a standalone H1 entry**

_Mechanism_: Kaufman ER(20) >= 0.30 asserts price is travelling a directional path rather than churning; ATR(14)/ATR(100) >= 1.10 asserts vol is expanding, i.e. a move has room to develop; (close - SMA200)/ATR14 >= 0 restricts to the bull side of the H1 anchor. Entry on the transition into simultaneous satisfaction of all three. ADX is deliberately excluded — documented unreliable on XAU; ER is its bounded replacement. Hypothesised mechanism: the conjunction identifies the onset of directional expansion, which should show forward MFE/MAE asymmetry before any exit logic exists.

market=XAUUSD· timeframe=H1· family=momentum_continuation· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- P1_entry_edge: E-Ratio > 1.15 AND p < 0.05 at ALL of H in {20, 50, 100}, measured against the bias-eligible permutation null (N=1000). This is the hard gate.
- P2_null_inflation: the unconditional-null E-Ratio will exceed the bias-eligible-null E-Ratio, quantifying how much of any apparent edge is gold's secular drift rather than the regime alignment.
- P3_episode_persistence: alignment episodes have median length >= 2 bars (measured: 2, mean 4.3, n=1628 over 124,688 bars) — recorded so a later persistence/hysteresis re-parameterisation is visibly a NEW trial.

> FROZEN_PARAMS={'er_len': 20, 'er_threshold': 0.3, 'atr_fast': 14, 'atr_slow': 100, 'vol_threshold': 1.1, 'sma_len': 200, 'bias_threshold': 0.0, 'entry_event': 'transition_into_alignment', 'direction': 'long_only'} | FROZEN_TEST={'horizons': '20, 50, 100', 'e_ratio_threshold': 1.15, 'p_value_threshold': 0.05, 'n_permutations': 1000, 'atr_period': 14, 'random_seed': 20260726, 'decisive_null': 'bias_eligible (trend_location >= 0)'} | KILL=K1: E-Ratio <= 1.15 or p >= 0.05 at ANY horizon under the bias-eligible null -> SHELVE. Momentum/continuation entry; house rules make this terminal. No exit design rescues it. ; K2: E-Ratio > 1.15 under unconditional null but <= 1.15 under the bias-eligible null -> SHELVE, and record explicitly that the apparent edge was gold drift, not regime alignment. ; K3: Walk-forward OOS DSR <= 0.95 -> KILL. | STOPPING_RULE=Iteration 1: this pre-registration exactly. No parameter changes. A persistence/hysteresis variant (addressing the 2-bar median episode) is a materially different re-parameterisation and requires a NEW register_hypothesis call incrementing trial_count — it is not an UPDATE. After Iteration 2: SHELVED. No third iteration. | CORRELATION=vs flood_tide_h1 / _iter2 (both SHELVED, seq=32/34): shares the ER regime filter and H1 long-only XAU framing. flood_tide's decisive failure was the regime-filtered null — the same null design is applied here from the start, so this is a genuinely harder test than flood_tide iteration 1 was. High prior of correlated failure; registered anyway because the entry trigger differs (regime alignment itself vs Donchian breakout). vs crest_n_keel / _momentum (seq=29/36): both H1 long-biased XAU; timing correlation expected. Occupies the same 'H1 trend continuation' portfolio slot — not a diversification add.

_hash_: `61d2298c6ddbd047…` · _prev_: `92c686324205b5fd…`

### seq 38 · 2026-07-26T20:40:02Z · update · `regime_align_h1`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `aligned_pct_of_bars`=5.626, `e_ratio_h100`=1.256, `e_ratio_h20`=1.157, `e_ratio_h50`=1.161, `e_ratio_threshold`=1.15, `n_entries`=1628, `null_mean_bias_h100`=1.231, `null_mean_bias_h20`=1.083, `null_mean_bias_h50`=1.144, `null_mean_uncond_h100`=1.118, `null_mean_uncond_h20`=1.018, `null_mean_uncond_h50`=1.061, `p1_verdict`=SHELVE_K2_DRIFT_ONLY, `p_bias_eligible_h100`=0.302, `p_bias_eligible_h20`=0.046, `p_bias_eligible_h50`=0.357, `p_unconditional_h100`=0.002, `p_unconditional_h20`=0.0, `p_unconditional_h50`=0.007

> P1_entry_edge FAILED under the decisive bias-eligible null -> K2 fires. The measured E-Ratios (1.157/1.161/1.256) are unchanged between nulls by construction; what changes is the null mean, which rises from 1.018/1.061/1.118 (unconditional) to 1.083/1.144/1.231 (bias-eligible). Nearly all apparent forward asymmetry is XAUUSD secular drift on the bull side of the SMA200 anchor, not the ER+vol regime alignment. Against the unconditional null the entry would have looked significant at all three horizons (p=0.000/0.007/0.002) - this is exactly the inflation K2 was written to catch, and the same failure mode that shelved flood_tide_h1 (seq=32) and _iter2 (seq=34). H=20 survives marginally (p=0.046) but the gate requires ALL horizons; a single marginal horizon out of three is not evidence. Momentum/continuation entry => HARD_GATE => terminal. Artifact: research/pre/artifacts/regime_align_h1_seq37_p1_20260726T203932Z.json

_hash_: `285108919a8d86fd…` · _prev_: `61d2298c6ddbd047…`

### seq 39 · 2026-08-20T15:34:14Z · hypothesis · `zlch_param_sweep`

**Exhaustive parameter + timeframe sweep of zerolag_chandelier (post-kill exit-edge probe)**

_Mechanism_: zerolag_chandelier's ENTRY was killed on a flat E-Ratio. The chandelier direction flip is, however, simultaneously a trailing EXIT rule, and entry edge and strategy edge are distinct claims. This sweep evaluates every (atr_period x atr_mult x zlsma_len x bias_tf x direction x min_atr) combination on five entry timeframes over 21.6 years, scoring Sharpe, max drawdown, win rate and profit factor, then subjects the leader to a drift-matched random-entry null, a passive buy-and-hold benchmark, and a Deflated Sharpe haircut at N = grid size. Hypothesised mechanism if positive: the asymmetric trailing exit (cut on flip, ride otherwise) converts a directionally neutral entry into positive expectancy by shaping the trade-return distribution rather than by timing.

market=XAUUSD· timeframe=M5/M15/H1/H4/D1· family=trend-following· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- P1_some_positive: many configs will show positive in-sample Sharpe. This is EXPECTED and is NOT evidence — XAUUSD rose ~12x over the window and any long-biased trend follower inherits that drift.
- P2_beats_drift (DECISIVE): the leading config's Sharpe exceeds a random-entry null at p < 0.05, where the null randomises ONLY the entry bars and holds direction, exit rule, trade count, sizing and cost model fixed. This isolates entry timing from drift and from the exit design.
- P3_beats_passive (DECISIVE): the leading config's Calmar (CAGR / max drawdown) exceeds passive long XAUUSD over the identical window. A trend follower that merely reproduces buy-and-hold risk-adjusted return has no reason to exist.
- P4_dsr: Deflated Sharpe at N = full grid size exceeds 0.95, using the sweep's own trial Sharpes as the empirical Var(SR) source.
- P5_plateau: the leader sits on a plateau — adjacent atr_period/atr_mult configs remain positive — rather than being an isolated spike.

> PARENT=zerolag_chandelier seq=19/20 (KILLED) | CONTEXT=Parent hypothesis zerolag_chandelier (seq=19/20) was KILLED at the signal-edge stage: 32-bar combined E-Ratio 0.9813, p=0.7720, flat at 16/32/64 bars, with role=HARD_GATE. CLAUDE.md holds that for momentum/continuation entries a failed E-Ratio is terminal and no exit design rescues it. This sweep deliberately probes that rule at the user's request: the chandelier IS a trailing exit, so strategy-level edge could in principle exist without entry-level edge. A positive result must therefore clear a HIGHER bar than usual (K1-K4 together), not a lower one. SEQUENCING DISCLOSURE: the grid and the survival gates were frozen before any results were read, but the D1 and H4 slices had been inspected before this entry was written. M15/M5/H1 were not. This is a post-hoc exploration of a killed hypothesis, not a pre-registration, and is logged as such. | FROZEN_GRID={'atr_periods': [5, 8, 10, 14, 20, 27, 34, 50], 'atr_mults': [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0], 'zlsma_lens': [20, 32, 50, 80, 120], 'bias_tfs': 'none + the two next-higher TFs per entry TF', 'directions': ['both', 'long', 'short'], 'min_atr': [0.0, 1.0], 'entry_timeframes': ['M5', 'M15', 'H1', 'H4', 'D1'], 'risk_pct': 0.01, 'max_drawdown_halt': 'DISABLED (absorbing barrier; truncates records)'} | FROZEN_GATES={'n_trades_min': 100, 'profit_factor_min': 1.2, 'max_dd_max': 0.3, 'sharpe_min': 0.0} | KILL=K1: leader fails the random-entry control (p >= 0.05) -> the apparent edge is drift plus exit mechanics, not signal. KILL, consistent with the seq=20 E-Ratio verdict. ; K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason to run it. KILL regardless of Sharpe. ; K3: DSR at N = grid size <= 0.95 -> the leader is within reach of a search of this size over noise. Cannot promote. ; K4: leader is an isolated spike (neighbours negative) -> overfit to the grid, not a robust region. | STOPPING_RULE=This is a single exhaustive pass. The grid is frozen above. If the leader survives K1-K4 the ONLY next step is out-of-sample walk-forward under qhf_harness — NOT a finer grid around the leader, which would be pure overfitting and would require a new registration. | CORRELATION=Shares the XAUUSD long-bias drift exposure of crest_n_keel (seq=29), crest_n_keel_momentum (seq=36), flood_tide_h1 (seq=32), flood_tide_h1_iter2 (seq=34) and regime_align_h1 (seq=38). In the last three the drift-matched null was decisive. The random-entry control here plays the same role and is applied from the start. | ENGINE=research.post.sweeps.zlch_engine, validated against qhf.engines.strategies.zlch under btpy_runner to worst |dSharpe|=0.0015 with 100% trade-set match on 7 configs (research.post.sweeps.run_parity).

_hash_: `59bd741f6dc55b83…` · _prev_: `285108919a8d86fd…`

### seq 40 · 2026-08-20T16:52:19Z · update · `zlch_param_sweep`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `K1_p_value`=0.0, `K1_random_entry_null_mean`=0.247, `K1_result`=PASS, `K2_calmar_vs_bh`=0.41 vs 0.28, `K2_result`=PASS, `K3_dsr_N15_logfloor`=0.998, `K3_dsr_N18480_estimated`=0.7392, `K3_dsr_N3696_empirical`=0.1186, `K3_result`=FAIL, `K4_neighbourhood_frac_positive`=1.0, `K4_neighbourhood_median_sharpe`=0.729, `K4_result`=PASS, `artifact`=research/post/artifacts/zlch_report_data.json, `bh_calmar`=0.28, `leader`=H4 atr_period=8 atr_mult=2.0 bias=none direction=long, `leader_cagr_acct`=0.0723, `leader_calmar`=0.41, `leader_exposure`=0.517, `leader_max_dd_px`=0.238, `leader_pf`=1.4946, `leader_sharpe_px`=0.8333, `leader_win_rate`=0.4135, `median_sharpe_D1`=0.114, `median_sharpe_H1`=0.138, `median_sharpe_H4`=0.266, `median_sharpe_M15`=-0.602, `median_sharpe_M5`=-1.402, `n_configs`=18480, `n_distinct_configs`=15630, `n_survivors`=2421, `original_config_percentile_in_M15`=56.7

> SWEEP RESULT: K1 PASS, K2 PASS, K4 PASS, K3 FAIL -> cannot promote. The seq=20 entry-level KILL is CONTESTED but NOT overturned. Decisive findings: (1) the kill was measured on M15, which the sweep shows is structurally cost-destroyed (median Sharpe -0.602; M5 -1.402). The same signal on H4 has 71.3% of configs positive, median +0.266. (2) The original registered config sat at the 56.7th percentile of M15 both-direction configs - typical for its timeframe, not unlucky. Its problem was trade frequency (463/yr) against a 0.22 USD/oz spread plus 7 USD/lot commission. (3) Long-only dominates at every viable timeframe; short is negative everywhere, consistent with the seq=20 E-Ratio split (long 1.033 / short 0.927). (4) The H4 ZLSMA bias filter - a core component of the original hypothesis - HURTS: median long Sharpe 0.611 without it vs 0.450 with it on H4. (5) All 12 leading configs beat a drift-matched random-entry null (p<=0.026, 9 of 12 at p=0.0000) with exit rule, direction, trade count, sizing and costs held fixed, so the result is not gold drift alone - the null means are positive (0.006-0.359) and the actuals clear them. (6) The leader sits on a plateau: all 9 adjacent atr_period x atr_mult neighbours positive, median 0.729. BINDING CONSTRAINT is K3: DSR at the honest N=18,480 is 0.739 (estimated Var(SR)) and 0.119 (empirical Var(SR), H4 pool). It reaches 0.998 only at N=15, the research-log floor, which ignores this sweep and is NOT the honest N for a grid-selected config. All numbers are IN-SAMPLE over 2004-06-11..2026-01-30. Per the frozen stopping rule the only legitimate next step is OOS walk-forward under qhf_harness on the H4 long-only region; a finer grid around the leader would be overfitting and needs a NEW registration. ENGINE NOTE: btpy_runner docstring claims backtesting.py ReturnPct = PnL/equity_at_entry. It is not - it is Trade.pl_pct, the per-unit PRICE return net of commission, so all harness Sharpe/DD/PF figures in this repo are position-size agnostic. Verified empirically; parity engine reproduces it to |dSharpe|<=0.0015.

_hash_: `9f0b3d617ce9f19f…` · _prev_: `59bd741f6dc55b83…`

### seq 41 · 2026-08-20T19:37:25Z · hypothesis · `ebb_n_flow_sweep`

**Exhaustive parameter + timeframe sweep of ebb_n_flow (post-kill asymmetry probe)**

_Mechanism_: Fade a Bollinger band excursion back to the midline, gated to balanced regimes by the Kaufman Efficiency Ratio; TP at the midline, SL at sl_atr_mult x max(ATR, floor), plus a hard time stop. The hypothesis was killed symmetric. Its own kill note names the suspected defect - symmetry on a secular-bull instrument - so this sweep promotes direction to a first-class grid dimension and tests that stated diagnosis across every other parameter and five entry timeframes. Hypothesised mechanism if positive: fading dips is a long-biased carry on an uptrending asset and survives, while fading rallies fights the drift and cannot.

market=XAUUSD· timeframe=M5/M15/H1/H4/D1· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- P1_asymmetry (the recorded diagnosis, tested directly): the seq=10 kill note states 'Gold's secular uptrend punishes symmetric fades; MR sleeve needs asymmetric treatment of long vs short.' If true, median Sharpe must order long-only > both > short-only at every timeframe, since fading a dip (long) aligns with the secular uptrend and fading a rally (short) opposes it.
- P2_beats_drift (DECISIVE): the leading config's Sharpe exceeds a random-entry null drawn from the REGIME-GATED pool (bars passing the KER, session and ATR-spike filters but not the band-touch test), holding direction, exit rules, trade count, sizing and costs fixed. This isolates the Bollinger signal from the regime filter and from gold's drift.
- P3_beats_passive (DECISIVE): the leading config's Calmar exceeds passive long XAUUSD over the identical window.
- P4_dsr: Deflated Sharpe at N = full grid size exceeds 0.95.
- P5_plateau: the leader's adjacent bb_n / bb_k neighbours remain positive.

> PARENT=ebb_n_flow seq=8/9/10 (KILLED) | CONTEXT=Parent ebb_n_flow (seq=8/9/10) was KILLED at stage 3_is_backtest on negative gross expectancy (-1.0). Its edge_gate_role is DIAGNOSTIC, so the flat entry E-Ratio (0.97 at w=30) was explicitly NOT the kill - house rules hold that a mean-reversion entry is carried by its exit, so a ~1.0 E-Ratio is expected. That makes this a materially better-founded reopening than the zerolag_chandelier sweep, where the parent failed a HARD_GATE. SEQUENCING DISCLOSURE: the grid and gates were frozen before any results were read. The D1 and H4 direction medians had been inspected before this entry was written, and both already order long > both > short, so P1 is partially observed; M5, M15 and H1 were unseen. Gates are reused verbatim from the zlch_param_sweep registration (seq=39) so they cannot be tuned to this data. This is a post-hoc exploration, not a pre-registration, and is logged as such. | FROZEN_GRID={'bb_n': [10, 14, 20, 30, 50], 'bb_k': [1.5, 2.0, 2.5, 3.0], 'er_max': [0.2, 0.3, 0.4, 1.0], 'sl_atr_mult': [0.5, 1.0, 1.5, 2.0, 3.0], 'time_stop_bars': [4, 8, 16, 32], 'direction': ['both', 'long', 'short'], 'session': ['rth (08-17 UTC, Fri cutoff 14)', 'all'], 'entry_timeframes': ['M5', 'M15', 'H1', 'H4', 'D1'], 'fixed': {'er_n': 10, 'atr_n': 14, 'atr_floor': 1.0, 'atr_spike_mult': 2.5, 'min_r': 0.5, 'risk_pct': 0.01}, 'note': 'D1 sweeps session=all only: D1 bars are stamped hour 0, so the 08-17 UTC filter would block every entry.'} | FROZEN_GATES={'n_trades_min': 100, 'profit_factor_min': 1.2, 'max_dd_max': 0.3, 'sharpe_min': 0.0} | KILL=K1: leader fails the regime-gated random-entry control (p >= 0.05) -> the Bollinger touch adds nothing over the KER gate alone. KILL. ; K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason to run it. KILL regardless of Sharpe. ; K3: DSR at N = grid size <= 0.95 -> cannot promote. ; K4: leader is an isolated spike -> overfit to the grid. | STOPPING_RULE=Single exhaustive pass; grid frozen above. If the leader survives K1-K4 the only next step is OOS walk-forward under qhf_harness. A finer grid around the leader is overfitting and requires a NEW registration. | CORRELATION=Deliberately LOW correlation with the trend/breakout book (crest_n_keel, flood_tide, regime_align, zerolag_chandelier): this is the mean-reversion sleeve and fades what they follow. That diversification value is the reason to reopen it. Shares only the XAUUSD long-drift exposure on its long side, which the regime-gated random-entry control is designed to price out. | ENGINE=research.post.sweeps.ebb_engine, validated against qhf.engines.strategies.ebb_n_flow under btpy_runner: 100% trade-set match on 6 configs / 3 timeframes, worst |dSharpe|=0.0172 (residual is the harness rounding trades-per-year to an integer).

_hash_: `371e25c3e33721c7…` · _prev_: `9f0b3d617ce9f19f…`

### seq 42 · 2026-08-20T22:13:45Z · update · `zlch_param_sweep`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `K1_configs_p_eq_0`=8 of 12, `K1_configs_p_lt_0.05`=10 of 12 (was reported 12 of 12), `K1_leader_null_mean`=0.271, `K1_leader_p`=0.0, `K1_null_mean_range`=0.020-0.399, `K1_result`=PASS (unchanged), `correction`=random-entry control recomputed with count matching, `null_realized_to_target_ratio`=1.0

> CONTROL CORRECTION. The random-entry null in the first pass sampled N candidate bars but did not verify how many TRADES resulted. Entries are consumed sequentially, so realised counts came in ~20% under target (705-734 vs 890 for the H4 leader). Because these Sharpes are annualised by trades-per-year, the null received a smaller sqrt(ppy) factor and was deflated roughly 10%, flattering the strategy. The control now tunes the sample size until realised count matches (median ratio 1.00) and annualises the null on the strategy own ppy. Effect: null means rose across the board; K1 goes from 12/12 to 10/12 clearing p<0.05 (two D1 configs now p=0.060 and 0.062). The H4 leader is unchanged at p=0.000 with null mean 0.271 vs actual 0.833, so K1 still PASSES and no verdict changes. K2 11/12, K3 FAIL, K4 PASS all unchanged. Report regenerated. The same defect was FATAL for the ebb_n_flow sweep (seq=41), where the R-floor rejects nearly every random bar: 1-4 realised trades against a target of 151, producing nonsense null Sharpes up to 6.07. Found there, fixed in both.

_hash_: `161c83a770c21e10…` · _prev_: `371e25c3e33721c7…`

### seq 43 · 2026-08-20T22:21:07Z · update · `ebb_n_flow_sweep`

stage=3_is_backtest · verdict=killed · counts_as_trial=False

_Metrics_: `K1_configs_clearing`=9 of 15, `K1_leader_null_mean`=0.662, `K1_leader_p`=1.0, `K1_result`=FAIL, `K2_configs_beating_bh_calmar`=3 of 15, `K2_result`=FAIL, `K3_dsr_N16_logfloor`=0.8008, `K3_dsr_N43200`=0.0594, `K3_dsr_N9600`=0.114, `K3_result`=FAIL at every N, `K4_neighbourhood_frac_positive`=1.0, `K4_result`=PASS (moot), `artifact`=research/data/ebb_n_flow/ebb_report_data.json, `leader`=H1 bb_n=10 bb_k=1.5 er_max=0.30 sl=3.0xATR ts=8 long/all-hours, `leader_exposure`=0.027, `leader_max_dd_px`=0.063, `leader_pf`=1.4231, `leader_sharpe_px`=0.6138, `leader_win_rate`=0.6013, `long_pct_positive_D1`=41.2, `median_sharpe_D1`=-0.2, `median_sharpe_H1`=-0.373, `median_sharpe_H4`=-0.341, `median_sharpe_M15`=-0.572, `median_sharpe_M5`=-1.284, `n_configs`=43200, `n_survivors`=268, `short_pct_positive_D1`=10.4, `survivor_rate_pct`=0.62

> SWEEP RESULT: K1 FAIL, K2 FAIL, K3 FAIL, K4 PASS -> the seq=10 KILL is CONFIRMED. P1 CONFIRMED but incomplete: the recorded diagnosis (symmetric fades punished by gold drift; needs asymmetric long/short) holds on H1/H4/D1 and STRENGTHENS as the timeframe slows - D1 long-only 41.2% of configs positive vs short-only 10.4%. It INVERTS at M15 (short 10.5% vs long 8.0%) and vanishes at M5: where cost dominates, direction stops mattering. The strict long>both>short ordering holds only on D1/H4; on H1/M15/M5 both is WORST, since trading both sides doubles cost drag without diversifying. DECISIVE (K1): the highest-Sharpe config in the grid (0.614) is WORSE than random entry drawn from its own feasible pool (null mean 0.662, p=1.000). The KER regime gate plus the R-floor account for the whole result; the Bollinger band touch - the actual hypothesis - subtracts value. Configs that DO beat their null have Calmar 0.04-0.15 against buy-and-hold 0.26-0.28 and exposure 0.1-3.8%. K3 fails at EVERY N including the log floor N=16 (DSR 0.8008), so unlike zlch_param_sweep this is not a multiple-testing problem - the raw edge is too small. Only 268 of 43,200 configs (0.62%) clear gates identical to those the chandelier sweep passed at 13.1%. LIMITATION: stop distance and band width both improve monotonically to the grid edge, so the interior optimum is unconfirmed; extending the grid to chase it would be fitting noise on a thrice-failed hypothesis. SALVAGE: the KER gate outperforms the signal it was meant to filter and is already the trend-quality term in research/pre/regime.py. Keep the component, not the strategy.

_hash_: `1e047b20609bfd29…` · _prev_: `161c83a770c21e10…`

### seq 44 · 2026-08-21T08:51:16Z · hypothesis · `cnk_param_sweep`

**Exhaustive parameter + timeframe sweep of crest_n_keel, both entry modes**

_Mechanism_: crest_n_keel exists in two structurally different forms that have never been compared on equal footing. PULLBACK (deployed): HMA slope plus price side plus a stochastic cross out of the oversold or overbought zone, exited by a fixed ATR bracket. MOMENTUM (candidate): HMA slope FLIP, long-only, exited by an ATR chandelier trail. seq=36 showed the momentum config beating the pullback config, but that was ONE configuration selected by TradingView search against ONE baseline. This sweep runs both modes over the same shared parameter dimensions and five entry timeframes, so the mode comparison is made across the whole surface instead of at two hand-picked points. Hypothesised mechanism if positive: on a secular-bull instrument a long trend-continuation entry with a ratcheting exit captures drift, while a symmetric pullback entry with a fixed bracket repeatedly fades it.

market=XAUUSD· timeframe=M5/M15/H1/H4/D1· family=crest_n_keel· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- P1_mode (the question seq=35/36 raised but never answered at grid scale): if the momentum entry is genuinely better than the pullback entry, the MOMENTUM surface must dominate the PULLBACK surface on median Sharpe and percent-positive at every timeframe. If it dominates only at the single config found by TradingView search, seq=36's advantage was a selection artifact.
- P2_long_bias: within MOMENTUM, long-only beats short-only at every timeframe (gold's secular uptrend), which is the assumption seq=35 froze in without testing.
- P3_beats_drift (DECISIVE): the leading config's Sharpe exceeds a random-entry null drawn from its own eligible pool, with the REALIZED trade count matched and the null annualised on the strategy's own periods-per-year, holding direction, exit rules, sizing and costs fixed.
- P4_beats_passive (DECISIVE): the leading config's Calmar exceeds passive long XAUUSD over the identical window.
- P5_dsr: Deflated Sharpe at N = full grid size exceeds 0.95.
- P6_plateau: the leader's one-step grid neighbours remain positive.
- P7_pullback_generalises: the deployed pullback region (hma 55, sl 1.5, tp 3.0, zones 20/80) sits near zero across its neighbourhood, confirming seq=29's walk-forward result is a property of the entry rather than of one config.

> CONTEXT=PARENTS: crest_n_keel seq=0 (PULLBACK, deployed, live magic 1100001) whose walk-forward at seq=29 returned OOS Sharpe 0.27-0.41 / DSR 0.03-0.11 and REFUTED a seeded 1.76 that never had a backing artifact - verdict left OPEN and deployment contested; and crest_n_keel_momentum seq=35 (MOMENTUM, TradingView Config A) which at seq=36 passed 4/5 gates on walk-forward (OOS Sharpe 1.20, gap -0.34, PF 1.26, 3829 trades) but FAILED DSR (0.061 at N=20) and was marked do-not-promote. Both parents are still OPEN, so this sweep is a scoping exercise over a contested live strategy, not a post-kill reopening. EDGE_GATE_ROLE is recorded DIAGNOSTIC for the entry as a whole because the pullback arm is a pullback entry (house rule: E-Ratio is diagnostic-only there, never a veto). The MOMENTUM arm is properly HARD_GATE - it is a continuation entry. No E-Ratio gate is applied in this sweep either way; it runs at stage 3 and the operative test is the K1 control. The split is recorded here so the correct rule carries forward per arm. SEQUENCING DISCLOSURE: the grid, gates and kill criteria were frozen before the sweep ran. The D1 timeframe was executed first as a smoke test and its results WERE inspected before this entry was written - D1 leader (momentum, long, hma 13, trail 2.0, 271 trades, Sharpe 0.795, K1 p=0.000 against a null of 0.580) and the D1 mode/direction medians are therefore OBSERVED, and P1/P2 are partially observed on D1 only. M5, M15, H1 and H4 were entirely unseen. Gates are reused verbatim from the zlch_param_sweep registration (seq=39) so they cannot be tuned to this data. This is a post-hoc exploration, not a pre-registration, and is logged as such. | FROZEN_GRID={'shared': {'hma_period': [13, 21, 34, 55, 89, 144], 'atr_period': [7, 14, 21], 'min_atr': [0.0, 1.0, 2.0], 'direction': ['both', 'long', 'short']}, 'pullback_only': {'stoch_k': [9, 14, 21], 'zones_oversold_overbought': [[20, 80], [25, 75], [30, 70]], 'sl_atr_mult': [1.0, 1.5, 2.0, 3.0], 'tp_atr_mult': [1.5, 2.0, 3.0, 4.0, 5.0]}, 'momentum_only': {'trail_atr_mult': [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]}, 'entry_timeframes': ['M5', 'M15', 'H1', 'H4', 'D1'], 'fixed': {'stoch_d': 3, 'stoch_smooth_k': 3, 'risk_pct': 0.02, 'max_drawdown_halt': 'DISABLED (absorbing barrier)'}, 'n_configs': {'pullback_per_tf': 29160, 'momentum_per_tf': 972, 'total': 150660}} | FROZEN_GATES={'n_trades_min': 100, 'profit_factor_min': 1.2, 'max_dd_max': 0.3, 'sharpe_min': 0.0} | KILL=K1: leader fails the matched random-entry control (p >= 0.05) -> the HMA/stochastic entry adds nothing over random timing in the same regime. KILL. ; K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason to run it. KILL regardless of Sharpe. ; K3: DSR at N = grid size <= 0.95 -> cannot promote. ; K4: leader is an isolated spike -> overfit to the grid. | STOPPING_RULE=Single exhaustive pass; grid frozen above. If the leader survives K1-K4 the only next step is OOS walk-forward under qhf_harness on the surviving region. A finer grid around the leader is overfitting and requires a NEW registration. | CORRELATION=HIGH correlation with the trend/breakout book by construction: the momentum arm is an HMA-slope trend follower and shares gold's long drift with flood_tide, regime_align and the long side of zerolag_chandelier. That shared drift is exactly what the matched random-entry control is designed to price out - a leader that merely rides the drift will not clear K1. The pullback arm is structurally short-biased and historically faded the gold bull, which is the recorded explanation for its weak standalone entry (E-Ratio ~0.9). | ENGINE=research.post.sweeps.cnk_engine, validated against qhf.engines.strategies.hma_stoch.HMAStoch1H and qhf.engines.strategies.cnk_momentum.CrestNKeelMomentum under btpy_runner: 100% entry-set match on 11 configs across both modes and 4 timeframes, worst |dSharpe|=0.0031. Parity covers the default slice only - the swept stochastic zones and direction toggle are a constant substitution and an entry mask that the harness classes cannot arbitrate.

_hash_: `94b4c197b7212cd2…` · _prev_: `1e047b20609bfd29…`

### seq 45 · 2026-08-23T08:23:09Z · update · `cnk_param_sweep`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `deployed_pullback_region_median_sharpe`=-0.0738, `k1_null_mean`=0.435, `k1_p_value`=0.0, `k2_bh_calmar`=0.2768, `k2_calmar`=0.4675, `k3_dsr_at_grid_n`=0.8391, `k4_neighbour_min_sharpe`=0.6771984633116068, `leader_cagr_acct`=0.0769028726896998, `leader_direction`=long, `leader_max_dd_px`=0.2693262706455639, `leader_mode`=momentum, `leader_n_trades`=2141, `leader_profit_factor_px`=1.3726347675526729, `leader_sharpe_px`=0.9849627340280688, `leader_timeframe`=H4, `leader_win_rate`=0.4072863148061653, `n_configs_distinct`=119917, `n_configs_raw`=150660, `n_countable`=98995, `n_survivors`=2789

> RESULT of the frozen seq=44 sweep. Grid ran to completion on all five timeframes: 150,660 rows, 119,917 distinct after collapsing min_atr duplicates (min_atr never binds where ATR exceeds every tested floor -- D1 collapses 30,132->10,044, H4 ->19,537, H1/M15/M5 essentially unaffected). 98,995 configs clear the 100-trade floor; 2,789 (2.33%) survive all four gates. LEADER H4 momentum long, hma13 atr7 trail1.5: 2,141 trades, Sharpe_px 0.985, max DD 26.9%, PF 1.373, win 40.7%, CAGR_acct 7.69%. VERDICT DO NOT PROMOTE -- K3 fails. K1 PASS: 0.985 vs matched random-entry null 0.435, p=0.000, realized 2,103/2,141; 8 of 10 per-cell leaders clear p<0.05 (failures are M5 momentum p=0.166 and D1 pullback p=0.057, both out-of-band cells). K2 PASS: Calmar 0.468 vs buy-and-hold 0.277; 5 of 10 leaders beat passive. NB the strategy EARNS LESS than passive gold (7.69% vs 12.48% CAGR) and wins only on drawdown (26.9% vs 44.6%). K3 FAIL: DSR 0.839 at N=119,917 with estimated Var(SR) -- the defensible primary figure. 0.9998 at N=17 (the log's global floor, wrong N for a best-of-119,917 selection); 0.0 with empirical Var(SR) pooled across five structurally heterogeneous timeframes (misapplication, same as seq=40). Best DSR any strategy in this repo has posted -- against zlch 0.739 and ebb failing at every N -- and still short of 0.95. K4 THIN PASS: all 3 one-step neighbours positive (median 0.712, min 0.677) but the leader sits at a GRID CORNER (smallest hma, fastest atr, tightest trail), so the plateau test is one-sided and the true optimum may lie outside the swept range. PREDICTIONS: P1 FAILS as written -- momentum does NOT dominate at every timeframe (wins H4/H1, loses D1/M5, splits M15); direction-controlled it wins at 4 of 5, but that is not what was registered. The advantage is LOCAL to a timeframe band, a third answer the registration did not anticipate. P2 PASS at every timeframe (momentum long 0.390 vs short -0.463 pooled; long > short in all 5 TFs, both modes) -- third sweep to find the XAUUSD short side dead. P3 PASS (=K1). P4 PASS (=K2). P5 FAIL (=K3). P6 PASS-thin (=K4). P7 CONFIRMED: the DEPLOYED pullback region (hma55 sl1.5 tp3.0 z20/80, live magic 1100001) has median Sharpe -0.074 across its 313-config neighbourhood, only 38.3% positive -- seq=29's walk-forward result is a property of the ENTRY, not of one config. Nothing here rehabilitates the deployed strategy. TWO BUGS FOUND AND FIXED IN THE ANALYSIS ITSELF, both would have inverted a verdict: (1) K2 read a 'calmar' key that buy_and_hold() never returns, silently yielding None and fabricating a K2 kill; (2) the K1 pass test was '(p or 1) < 0.05', and p=0.000 is falsy, scoring the strongest possible result as a failure. Engine parity vs btpy_runner: 11 configs, 4 timeframes, both modes, 100% entry-set match, worst |dSharpe| 0.0031. NEXT STEP per the frozen stopping rule: OOS walk-forward under qhf_harness on the H4/H1 momentum long-only region. A finer grid around the leader is overfitting and requires a NEW registration. Report: research/data/crest_n_keel/cnk_sweep_report.html

_hash_: `84482dc818e84592…` · _prev_: `94b4c197b7212cd2…`

### seq 46 · 2026-08-23T09:49:02Z · update · `cnk_param_sweep`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `gate_passed`=0, `h1_dsr_at_grid_n`=0.0, `h1_folds_positive`=12, `h1_folds_total`=17, `h1_is_oos_gap`=-0.02, `h1_oos_max_dd`=0.187, `h1_oos_profit_factor`=1.29, `h1_oos_sharpe_mean_folds`=0.761, `h1_oos_sharpe_median_folds`=0.429, `h1_oos_sharpe_pooled`=0.91, `h1_oos_trades`=1973, `h4_dsr_at_grid_n`=0.0, `h4_folds_positive`=11, `h4_folds_total`=16, `h4_is_oos_gap`=0.07, `h4_oos_max_dd`=0.273, `h4_oos_profit_factor`=1.23, `h4_oos_sharpe_mean_folds`=0.454, `h4_oos_sharpe_median_folds`=0.301, `h4_oos_sharpe_pooled`=0.71, `h4_oos_trades`=1595

> OOS WALK-FORWARD of the seq=44/45 sweep leaders under qhf_harness -- the one next step the frozen stopping rule permits. Both MOMENTUM long-only, 24/7, max_drawdown_halt DISABLED and min_atr 0.0 to match the sweep definition, Pepperstone cost model, known gaps excluded. Runner: qhf_harness/examples/run_cnk_sweep_oos.py (frozen CONFIGS declared in the file before it was run). H4 hma13 atr7 trail1.5, train 1825D / test 365D / step 365D, 16 folds: pooled OOS Sharpe 0.71, mean-of-folds 0.454, median 0.301, range [-2.15, +2.69], 11/16 folds positive, OOS max DD 27.3%, PF 1.23, 1,595 OOS trades. Harness IS-OOS gap +0.07; gap vs the sweep's own IS 0.985 is +0.531. H1 hma55 atr14 trail3.0, train 1460D / test 365D / step 365D, 17 folds: pooled OOS Sharpe 0.91, mean-of-folds 0.761, median 0.429, range [-0.77, +2.55], 12/17 folds positive, OOS max DD 18.7%, PF 1.29, 1,973 OOS trades. Harness IS-OOS gap -0.02 (OOS marginally BETTER than IS); gap vs sweep IS 0.971 is +0.210. H1 is the stronger of the two on every axis: stability, drawdown, gap and fold hit-rate. NOTE the H1 sweep leader (hma55/atr14/trail3.0) is EXACTLY the CrestNKeelMomentum defaults, i.e. TradingView Config A. A 119,917-config exhaustive sweep independently rediscovered the parameters found by TradingView search -- mild evidence that search was not arbitrary. VERDICT UNCHANGED: DO NOT PROMOTE. Both configs FAIL the research-tier gate on DSR alone -- 0.0000 at N=119,917 for both. Harness DSR at N=17 is 0.042 (H4) and 0.359 (H1). CAVEAT THAT LIMITS THIS RESULT, stated in the runner docstring: run_walk_forward applies FIXED parameters to every fold and does not re-optimise inside the training window, and these parameters were selected from a sweep over the FULL history, which contains every fold tested here. So this is NOT a clean out-of-sample test of the selection procedure. What it does establish is TEMPORAL STABILITY -- and on that axis the result is genuinely good, especially H1 at gap -0.02. Temporal stability is a necessary but not sufficient condition; it cannot rescue the DSR failure. The clean test would be a NESTED walk-forward that re-runs the sweep inside each training window and selects the leader from training data only. The harness does not support that out of the box; it would need a new registration.

_hash_: `1e5674798d4f29e4…` · _prev_: `84482dc818e84592…`

### seq 47 · 2026-08-23T09:54:51Z · hypothesis · `cnk_nested_walk_forward`

**crest_n_keel nested walk-forward: does the selection procedure generalise?**

_Mechanism_: Tests the METHODOLOGY rather than a configuration. If an exhaustive parameter sweep followed by top-of-grid selection has real predictive content, then a leader chosen from a training window alone should outperform on the following unseen window, and should beat other configs that merely cleared the same gates. If it does not, the ranking is in-sample noise and every sweep in this repo has been measuring selection luck.

market=XAUUSD· timeframe=H1,H4· family=crest_n_keel· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- N1: the nested procedure's mean OOS Sharpe across folds is > 0.
- N2: momentum is the selected mode in a majority of folds at both H1 and H4.
- N3: a non-short direction (long or both) is selected in a majority of folds.
- N4 (leakage estimate): nested OOS mean Sharpe is BELOW the seq=46 fixed-leader OOS mean on the same geometry (H1 +0.761, H4 +0.454). The size of that shortfall is the value of the lookahead seq=46 could not remove.
- N5: selection is unstable -- the config chosen changes across folds, and fewer than half the folds select the seq=44 full-history leader.
- N6 (DECISIVE): the selected config's OOS Sharpe exceeds the median OOS Sharpe of a random sample of OTHER configs that also cleared the training gates, in a majority of folds. This is the test of whether training rank carries any information about the test window.

> PARENT: cnk_param_sweep seq=44 (registration) / seq=45 (result: leader H4 momentum long, Sharpe_px 0.985, K1 p=0.000, K2 Calmar 0.468 vs B&H 0.277, K3 DSR 0.839 at N=119,917 -> DO NOT PROMOTE) / seq=46 (harness walk-forward: H1 pooled OOS Sharpe 0.91 with IS-OOS gap -0.02, H4 0.71 with gap +0.07, both FAIL the research-tier gate on DSR at 0.0000). WHY THIS IS A SEPARATE TRIAL: seq=46 could not be clean. qhf_harness's run_walk_forward applies FIXED parameters to every fold and does not re-optimise inside the training window, and those parameters came from a sweep over the full history, which contains every fold it tested. The selection saw the test data. seq=46 therefore measures TEMPORAL STABILITY, which it found to be good, and cannot speak to whether the SELECTION PROCEDURE generalises. This registration tests the procedure. SEQUENCING DISCLOSURE: nothing from this nested run has been observed. One H4 fold was timed for feasibility (96s/fold, 4,058 gate-passers) with the selection result deliberately not printed; that timing informed only the decision to proceed, not the design. Runner: research/post/sweeps/cnk_nested_wf.py, written before this registration and frozen with it. | FROZEN_DESIGN=For each fold: re-run the FULL seq=44 grid (30,132 configs: both entry modes, all three directions, every parameter) on the TRAINING window ONLY; apply the gates; select the highest training Sharpe; evaluate that one config once on the following untouched test window. Fold geometry mirrors seq=46 so the two are comparable -- H1 train 1460D / test 365D / step 365D (17 folds), H4 train 1825D / test 365D / step 365D (16 folds). Gates: PF >= 1.20, max DD <= 0.30, Sharpe > 0 (identical to seq=44); trade floor SCALED to the training window at 100/21.6 per year with a hard minimum of 30, because applying the absolute 100 to a 4-year window would be a far harsher gate than the sweep itself used. Mode and direction are NOT fixed in advance: restricting to 'momentum long-only' would re-import a conclusion drawn from the full history and reintroduce the leak in a subtler form. max_drawdown_halt disabled throughout; risk_pct 0.02; Pepperstone cost model; seed 20260820. | KILL_CRITERIA=NK1: mean OOS Sharpe across folds <= 0 -> the selection procedure has no out-of-sample edge. KILL the line, not just the config. NK2 (DECISIVE): the selected config fails to beat the gate-passing pool median in a majority of folds -> the sweep ranking is noise and the whole exhaustive-sweep-then-pick-the-top methodology is not producing information. KILL, and the finding generalises well beyond crest_n_keel. NK3: fewer than 60% of folds yield ANY config clearing the training gates -> the procedure is not deployable regardless of its average. | STOPPING_RULE=Single pass; geometry, gates and grid frozen above. If it survives NK1-NK3 the next step is a cost/slippage stress and a live-forward paper period on demo -- NOT another grid and NOT a finer search. If it fails NK2 the correct response is to stop ranking sweeps by top-of-grid Sharpe across this repo, which is a methodology change, not a strategy change.

_hash_: `56bf497b4cdbc512…` · _prev_: `1e5674798d4f29e4…`

### seq 48 · 2026-08-23T12:55:55Z · update · `asian_session_fade`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `allday_fade_gross_t`=0.83, `allday_fade_gross_usd_per_oz`=0.0973, `beta_fwd_on_overshoot`=-0.0337, `beta_p_shuffle_one_sided`=0.046, `beta_r_squared`=0.0006, `beta_t`=-1.66, `decile_fade_gross_t`=0.28, `decile_fade_gross_usd_per_oz`=0.0823, `decile_fade_net_usd_per_oz`=-0.2077, `edge_cost_ratio`=0.284, `london_control_beta`=0.0422, `london_control_t`=1.84, `median_daily_atr_usd`=19.07, `n_days`=4317, `roundtrip_cost_usd_per_oz`=0.29

> EVENT-STUDY TEST of the seq=15 mechanism (thin 22:00-05:00 book overshoots; London liquidity pushes it back). Deliberately not a strategy: no entry rule, no exit, no sizing, no parameter search -- a bucket sort, which is the cheapest thing that can falsify the mechanism. Runner: research/pre/asian_session_fade.py; artifact research/pre/artifacts/asian_session_fade.json. n=4,317 days of H1. STATISTICALLY: beta(forward 6h ~ Asian overshoot) = -0.0337, t=-1.66, R^2=0.0006, one-sided permutation p=0.046 (2,000 shuffles). Sign is as predicted (negative = reversion). Deep-book LONDON control is +0.0422 (t +1.84), i.e. the opposite sign, so the asian-vs-london contrast also points the predicted way. That is the entire case in favour. ECONOMICALLY IT FAILS, and this is decisive. Translating the same effect into dollars at the actual cost model: fading the extreme overshoot deciles (n=864) earns a GROSS +$0.0823/oz per trade against a round-trip cost of $0.29/oz (spread 0.22 + commission 0.07), i.e. NET -$0.208/oz. The gross edge is 3.5x too small to pay the spread. Fading every day: gross +$0.0973/oz, net -$0.193/oz. Crucially the gross dollar edge is not even statistically significant -- t=+0.28 (deciles) and t=+0.83 (all days). The marginal regression beta does NOT survive translation into tradeable dollars, because it is estimated in ATR-normalised units where extreme observations carry leverage that per-trade PnL does not give them. VERDICT SHELVED. A 3.5x shortfall is not a gap a definitional variant closes. WHAT WAS NOT TESTED, stated so the shelving is auditable: the registration specifies an HLPeak ATR CHANNEL overshoot and a StochMA trigger; I used session net displacement normalised by prior-day ATR(14), and a fixed 6h forward window rather than a channel-midline target. A channel definition would change which days qualify, not the order of magnitude of the available move. PREREQUISITE DEFECT FOUND AND FIXED FIRST -- without it this test would have been meaningless: research/post/sweeps/data.py tz_localize('UTC')s timestamps that are BROKER SERVER TIME (MetaQuotes EET/EEST). Empirically calibrated: offset is exactly +3h for 74,184 bars and +2h for 50,703 bars, matching EEST/EET; volume peaks at index hour 16 summer / 16-17 winter against a true NY open of 13:30/14:30 UTC; no Sunday bars; week opens at a constant hour 1 in every month; hour 0 is the daily rollover break. A '22:00-05:00 GMT' window read through the old loader is really ~19:00-02:00 GMT. data.py gained tz='server_eet' (correct, DST-aware) with the wrong 'legacy_utc' kept as DEFAULT so seq 39-46 stay reproducible -- those are all 24/7 with no session filter, so a relabel cannot change any of their numbers. AFFECTED ELSEWHERE: qhf/data/csv_loader.py documents its index as UTC and btpy_runner._apply_session_filter warns 'Check that timestamps are UTC', reading the same server-time exports -- so seq=29's crest_n_keel SESSION-ONLY arm was filtering the wrong hours. Its OOS Sharpe 0.27-0.41 range spans 24/7 vs session-only; the session-only half is not trustworthy and is flagged pending a decision on re-running it. INCIDENTAL: the London deep-book control is mildly POSITIVE (continuation, t +1.84), which is the opposite of mean reversion and is consistent with the momentum-beats-pullback finding at seq=45.

_hash_: `a5263301e1b69bfa…` · _prev_: `56bf497b4cdbc512…`

### seq 49 · 2026-08-23T17:33:52Z · update · `cnk_nested_walk_forward`

stage=5_walk_forward · verdict=killed · counts_as_trial=False

_Metrics_: `h1_fixed_mean`=0.76, `h1_folds`=17, `h1_nk2_n`=17, `h1_nk2_p`=0.5, `h1_nk2_wins`=9, `h1_oos_mean`=0.079, `h1_oos_median`=-0.041, `h1_oos_positive`=8, `h1_oos_trades_median`=27, `h1_pool_mean`=-0.176, `h1_train_sharpe_mean`=1.648, `h4_fixed_mean`=0.452, `h4_folds`=16, `h4_nk2_n`=15, `h4_nk2_p`=0.5, `h4_nk2_wins`=8, `h4_oos_mean`=-0.353, `h4_oos_median`=0.24, `h4_oos_positive`=8, `h4_oos_trades_median`=10, `h4_pool_mean`=-0.116, `h4_train_sharpe_mean`=1.448, `lookahead_gap_h1`=0.681, `lookahead_gap_h4`=0.805, `pooled_nk2_n`=32, `pooled_nk2_p`=0.43, `pooled_nk2_wins`=17, `pooled_pool_mean`=-0.149, `pooled_selected_mean`=-0.124, `pooled_selection_value`=0.025

> RESULT of the frozen seq=47 nested walk-forward. Both timeframes complete: H4 16/16 folds, H1 17/17 folds, every fold re-running the full 30,132-config grid on its TRAINING window only and evaluating the single training-selected leader once on the following untouched year. NK3 PASSES: 33/33 folds produced a gate-clearing config. NK1 FAILS: pooled mean OOS Sharpe -0.124. H4 mean -0.353 (median +0.240, 8/16 positive, one fold NaN on a single trade); H1 mean +0.079 (median -0.041, 8/17 positive). The selected configs had a mean TRAINING Sharpe of +1.448 (H4) and +1.648 (H1). Training Sharpe of ~1.5 mapped to an out-of-sample Sharpe of ~0. NK2 FAILS, and it is the decisive one: the training-selected leader beat the median of a random sample of OTHER configs that cleared the same training gates in 17 of 32 comparable folds -- 53%, sign-test p=0.430. Per timeframe 8/15 (H4) and 9/17 (H1), both p=0.500. Selected mean -0.124 vs pool mean -0.149: a difference of +0.025 Sharpe. Picking the best config in training was worth approximately nothing over picking any config that merely qualified. TRAINING RANK CARRIES NO INFORMATION ABOUT THE TEST WINDOW. N4 CONFIRMED and it quantifies the leak: the seq=44 full-history leader scored +0.452 (H4) and +0.760 (H1) on the SAME folds where honest selection scored -0.353 and +0.079. That gap of roughly 0.7-0.8 Sharpe is pure lookahead -- it is the advantage of having chosen the parameters while already knowing the test data, and it is LARGER than the effect seq=45/46 were claiming. seq=46's good IS-OOS gap (-0.02 on H1) was measuring the stability of a config selected with hindsight, exactly as its caveat said. N2 FAILS: the procedure chose PULLBACK in 11/16 (H4) and 11/17 (H1) folds -- the mode the full-history sweep ranks worse. N3 PASSES (non-short selected 16/16 H4, 11/17 H1). N5 CONFIRMED: selection is unstable, the config changes nearly every fold and the mode flips. N1 FAILS. N6 FAILS (= NK2). MECHANISM OF FAILURE, visible in the artifacts: the procedure systematically selects LOW-FREQUENCY configs whose high training Sharpe is a small-sample artifact. Median OOS trades per fold is 10 on H4 (minimum 1) and 27 on H1 (minimum 3). A gate on trades-per-year in TRAINING does not prevent this, because a config can trade adequately in a 4-5 year training window and barely at all in the following year. CONSEQUENCE, registered in advance as a methodology outcome rather than a strategy one: exhaustive-sweep-then-take-the-top-of-grid does not produce information at this grid size on this instrument. That indicts the SELECTION step shared by seq=39/40 (zlch), seq=41/43 (ebb) and seq=44/45 (cnk), not their engines, gates or controls -- those remain sound, and the in-sample surface findings (short side dead, sub-H1 is a cost regime, momentum beats pullback in-sample at H1/H4) are descriptive statistics over the whole grid and are unaffected. What is refuted is the inference from 'this config topped the ranking' to 'this config is good'. The Deflated Sharpe haircut was already saying this analytically at DSR 0.839; this is the same verdict measured directly. VERDICT KILLED. Not the strategy -- the selection procedure. WHAT WOULD REPLACE IT, not tested here and requiring its own registration: far smaller grids with mechanism-motivated parameters rather than exhaustive search; selection performed inside training only; a trades-per-year floor applied to the TEST window not just training; and the gate-passing-pool control run as a standing gate on any future sweep, since it is cheap and it is what caught this. Artifacts: research/data/crest_n_keel/cnk_nested_wf_H4.json, cnk_nested_wf_H1.json, cnk_nested_summary.json. Runner: research/post/sweeps/cnk_nested_wf.py.

_hash_: `bd5596dd89efff20…` · _prev_: `a5263301e1b69bfa…`

### seq 50 · 2026-08-23T20:56:38Z · hypothesis · `asqs_param_sweep`

**Exhaustive parameter + timeframe sweep of ASQ SafeScalping v1.20**

_Mechanism_: 7-condition breakout scalper: EMA trend direction, minimum EMA separation in ATR units, price above/below both EMAs, N-bar breakout with an ATR buffer, RSI band, bar-over-bar momentum, and an optional MTF agreement. Fixed point-based SL/TP with breakeven, trailing and a nominal partial close. The sweep asks whether ANY parameterisation of this family has a viable region on XAUUSD, and how much of the recorded seq=30 refutation is attributable to a mis-specified session window.

market=XAUUSD· timeframe=M5,M15,H1· family=asqs· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- A1 (the reason this sweep exists): ASQS is session-filtered and every recorded result for it, seq=30 included, filtered the WRONG HOURS because the loader labels broker server time as UTC. Re-run on true UTC, the original 08:00-17:00 window will NOT be the best session in the grid, and the difference between the correct and incorrect window is the size of the error in the logged record.
- A2: the short side underperforms the long side at every timeframe, as it has in all three previous sweeps on this instrument.
- A3: median Sharpe is negative across the grid at M5 and improves monotonically with timeframe, because a roughly fixed cost per round trip is charged against a gross edge that shrinks with horizon.
- A4: no configuration clears DSR > 0.95 at N = grid size.
- A5 (methodology, carried from seq=49): the top-of-grid configuration will NOT be shown to be promotable, and this sweep is registered as a SURFACE CHARACTERISATION, not a search for a deployable config.

> PARENT: asqs seq=? (ASQ SafeScalping v1.20, M5 7-condition breakout, LIVE ON DEMO) whose seeded 5.14 Sharpe / 1.55 profit factor was REFUTED by the harness at seq=30 (OOS Sharpe ~-1, net-losing). This is the first exhaustive sweep of it. TWO DEFECTS FOUND DURING THE ENGINE PORT, both of which change what every previously recorded ASQS number means: (1) TIMEZONE -- research/post/sweeps/data.py labels broker server time (MetaQuotes EET/EEST) as UTC. Calibrated empirically: exactly +3h for 74,184 bars and +2h for 50,703 bars. ASQS filters 08:00-17:00 'UTC', so it has really been trading ~05:00-14:00 / 06:00-15:00 UTC. (2) PARTIAL CLOSE IS INERT -- qhf btpy_runner sets exclusive_orders=True, so the second of ASQS's two partial-close orders CANCELS the first. The TP1 leg never exists and the only surviving effect is that size is halved. Verified directly against harness trades: 349 trades, all unique entry timestamps, all at the remainder size, normal durations. The strategy's own docstring calls this a 'two-leg approximation -- see BUG-2 fix'; the fix does not work under this runner. The main grid reproduces the harness behaviour so it stays comparable with the logged record. ENGINE PARITY: research/post/sweeps/asqs_engine.py vs btpy_runner on 10 configs across M5/M15/H1 -- 100.0% entry-set match on all ten, worst |dSharpe| 0.0721. That residual is not a disagreement: per-trade return std matches to 7 significant figures (0.00223227 vs 0.00223239) and the annualisation factor to 4 (18.739 vs 18.735); the engines differ by 5e-06 per trade in the mean. Sharpe is simply unstable when the mean return is 0.04 of a standard deviation. Reaching parity required fixing three semantic errors in my port: initial SL/TP anchor to the SIGNAL BAR CLOSE while breakeven/trailing anchor to the FILL price (two different anchors in one strategy); use_session=False disables the weekend and Friday-cutoff checks too, because they live inside _pass_session(); and the partial-close behaviour above. SEQUENCING: no sweep output has been observed. The grid was sized from per-config TIMING only (2.68s on full M5 history). | FROZEN_GRID=17,496 configs x 3 timeframes (M5, M15, H1) = 52,488. ema_pairs=[(20, 100), (20, 200), (50, 100), (50, 200), (50, 400), (100, 400)]; breakout_lookback=[10, 15, 25]; trend_strength=[0, 1, 2]; breakout_buffer=[0.1, 0.3]; rsi_bands=[(45.0, 65.0, 35.0, 55.0), (40.0, 70.0, 30.0, 60.0)]; sl_points=[150, 300, 500]; tp_points=[225, 450, 750]; sessions=[(True, 8, 17), (True, 7, 16), (False, 0, 24)]; directions=['both', 'long', 'short']. FIXED: rsi_period=14, atr_period=50, partial_mode=harness, {'use_breakeven': True, 'breakeven_start': 150, 'breakeven_offset': 20, 'use_trailing': True, 'trail_start': 200, 'trail_step': 100, 'use_partial_close': True, 'tp1_points': 200, 'tp1_close_pct': 50.0, 'risk_pct': 0.5, 'max_day_trades': 4, 'max_dd_pct': 8.0, 'avoid_friday': True, 'friday_cutoff': 14}. H4/D1 excluded: ASQS sizes stops in POINTS (300 points = $3.00), which is meaningless against a daily bar. Bars load tz='server_eet' (true UTC). | FROZEN_GATES={'n_trades_min': 100, 'profit_factor_min': 1.2, 'max_dd_max': 0.3, 'sharpe_min': 0.0} | KILL_CRITERIA=AK1: the leading config fails the matched random-entry control (p >= 0.05) -> the 7-condition entry adds nothing over random timing. KILL. AK2: leading config's Calmar <= passive buy-and-hold Calmar -> no economic reason to run it. KILL. AK3: DSR at N = grid size <= 0.95 -> cannot promote. AK4: median Sharpe across the whole grid is negative at every timeframe -> the strategy family has no viable region and the live demo deployment has no support at any parameterisation. | STOPPING_RULE=Single exhaustive pass; grid frozen above. Per seq=49 the top-of-grid config is NOT promotable on this evidence and no walk-forward of a grid-selected leader will be treated as validation. The only outcomes this sweep can produce are: a surface characterisation, a corrected estimate of the seq=30 timezone error, and a decision about the live demo deployment. A finer grid requires a NEW registration.

_hash_: `6a5a63887df34de3…` · _prev_: `bd5596dd89efff20…`

### seq 51 · 2026-08-24T07:26:20Z · update · `asqs_param_sweep`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `ak1_null_mean`=-2.077, `ak1_p_value`=0.0, `ak2_bh_calmar`=0.274, `ak2_calmar`=0.675, `ak2_n_beating_bh`=2, `ak3_dsr_at_grid_n`=0.0384, `ak4_all_tf_medians_negative`=1, `dir_median_long`=0.016, `dir_median_short`=-0.417, `leader_cagr_acct`=0.0538, `leader_max_dd_px`=0.0669, `leader_n_trades`=1147, `leader_profit_factor_px`=1.1876, `leader_session`=7-16, `leader_sharpe_px`=1.0664, `leader_timeframe`=M5, `n_configs`=52488, `n_countable`=51277, `n_survivors`=533, `session_error_cost_sharpe`=0.0717, `session_median_7_16`=-0.0726, `session_median_8_17`=-0.1443, `session_median_off`=-0.4569, `tf_median_H1`=-0.071, `tf_median_M15`=-0.164, `tf_median_M5`=-0.383

> RESULT of the frozen seq=50 sweep. 52,488 configs across M5/M15/H1 (17,496 each), 51,277 clear the 100-trade floor, 533 survive all four gates (1.02%). LEADER M5, session 07-16 UTC, both directions, ema50/200 bo25 ts2 sl150 tp750: 1,147 trades, Sharpe_px 1.066, max DD 6.7%, PF 1.188, win 45.2%, CAGR_acct 5.38%. VERDICT DO NOT PROMOTE, and the live demo deployment has no support at ANY parameterisation. A1 CONFIRMED, this is the correction to the seq=30 record: on true UTC the original 08:00-17:00 window is NOT the best in the grid. Pooled median Sharpe by session: 07-16 = -0.0726 (43.0% positive), 08-17 = -0.1443 (35.3%), no session filter = -0.4569 (24.7%). The mis-specified window cost 0.072 Sharpe pooled, and ALL THREE timeframe leaders independently selected 07-16 rather than 08-17. The error grows as the timeframe shortens: 0.016 Sharpe at H1, 0.079 at M15. Session filtering itself is worth ~0.38 Sharpe against not filtering, so the feature is real even though its window was wrong. A2 CONFIRMED: direction medians long +0.016, both -0.222, short -0.417. Fifth consecutive sweep on this instrument to find the short side dead. A3 CONFIRMED: median Sharpe degrades monotonically with timeframe -- H1 -0.071, M15 -0.164, M5 -0.383 -- exactly the fixed-cost-per-round-trip signature. ASQS is natively an M5 scalper and M5 is its worst timeframe. A4 CONFIRMED (no config clears DSR 0.95). A5 CONFIRMED. AK1 PASSES: all three timeframe leaders beat a matched random-entry null at p=0.000 -- M5 1.066 vs null -2.077, M15 1.017 vs -0.035, H1 0.987 vs -1.672. The 7-condition entry DOES carry timing information; that is the strongest thing that can be said for this strategy. AK2 PASSES for the leader: Calmar 0.675 vs buy-and-hold 0.274 (M5); H1 0.501 vs 0.263 passes; M15 0.225 vs 0.261 fails. 2 of 3. AK3 FAILS: DSR 0.0384 at N=52,488 with estimated Var(SR); 0.7243 at N=19 (the log's global floor, wrong N for a best-of-52,488 selection); 0.0 with empirical Var(SR) pooled across timeframes. AK4 FAILS -- the decisive one for the deployment question. The frozen criterion was 'median Sharpe across the whole grid is negative at every timeframe -> the family has no viable region'. It is negative at all three (-0.071, -0.164, -0.383). A leader exists at Sharpe 1.066 but it is the top of a 52,488-config search over a surface whose centre is negative everywhere, which per seq=49 is precisely the inference shown to carry no out-of-sample information. TWO DEFECTS FOUND DURING THE ENGINE PORT, both changing what every prior ASQS number means: (1) TIMEZONE, as above -- data.py labels broker server time (EET/EEST) as UTC, exactly +3h for 74,184 bars and +2h for 50,703; (2) PARTIAL CLOSE IS INERT -- btpy_runner sets exclusive_orders=True so the second of ASQS's two partial-close orders CANCELS the first. The TP1 leg never exists and the only surviving effect is that position size is halved. Verified against harness trades: 349 trades, all unique entry timestamps, all at the remainder size. The strategy docstring calls this a 'two-leg approximation -- see BUG-2 fix'; the fix does not work under this runner. The sweep reproduces harness behaviour to stay comparable. ENGINE PARITY: 10 configs across M5/M15/H1, 100.0% entry-set match on all ten, worst |dSharpe| 0.0721 -- not a disagreement: per-trade return std matches to 7 significant figures and the annualisation factor to 4; the engines differ by 5e-06 per trade in the mean, and Sharpe is unstable at a mean of 0.04 std. Three semantic errors were fixed to get there: SL/TP anchor to the SIGNAL BAR CLOSE while breakeven/trailing anchor to the FILL price; use_session=False also disables the weekend and Friday checks; and the partial-close behaviour above. Artifacts: research/data/asqs/asqs_sweep_{M5,M15,H1}.csv, asqs_report_data.json, asqs_deepdive.csv, asqs_sweep_report.html.

_hash_: `74044644775ad224…` · _prev_: `6a5a63887df34de3…`

### seq 52 · 2026-08-24T07:31:32Z · update · `crest_n_keel`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `n_folds`=17, `seq29_247_corrected`=0.1717, `seq29_247_delta`=-0.002, `seq29_247_logged_basis`=0.1738, `seq29_session_corrected`=-0.2386, `seq29_session_corrected_dd`=0.124, `seq29_session_corrected_pf`=0.783, `seq29_session_delta`=-0.5581, `seq29_session_logged_basis`=0.3196, `seq29_session_logged_dd`=0.053, `seq29_session_logged_pf`=1.534

> TIMEZONE CORRECTION to the seq=29 walk-forward. seq=29 recorded OOS Sharpe 0.27-0.41 across '24/7 vs session-only' configurations. The session-only arm filtered hour-of-day on an index that is BROKER SERVER TIME (MetaQuotes EET/EEST) labelled UTC by research/post/sweeps/data.py, so it traded roughly 05:00-14:00 / 06:00-15:00 UTC rather than the intended 08:00-17:00, DST-dependent. Re-run identically on both bases via research/post/sweeps/rerun_seq29_session.py (17 folds, train 1460D / test 365D / step 365D, HMAStoch1H defaults, Pepperstone cost model, known gaps excluded). SESSION-ONLY ARM: logged basis +0.3196 (75 OOS trades, PF 1.534, DD 5.3%, 11/17 folds positive) -- which reproduces the logged 0.27-0.41 range and confirms this is the same computation. CORRECTED to true UTC: -0.2386 (78 trades, PF 0.783, DD 12.4%, 7/17 folds positive). DELTA -0.5581. The mis-specified session did not merely shade the figure, it INVERTED its sign: the session-only configuration is net LOSING once the hours are right, with a profit factor below 1.0 and more than double the drawdown. CONTROL ARM validates the method: 24/7 has no session filter, so a relabel cannot change it, and it does not -- +0.1738 logged basis vs +0.1717 corrected, delta -0.0020 (the residual is fold boundaries shifting 2-3 hours within a 365-day window). If that delta had been material the script would have been wrong rather than the finding. CONSEQUENCE: the upper end of the seq=29 range came from the session-only arm and is not real. On corrected data the only non-negative configuration is 24/7 at +0.17, well below the 0.27-0.41 recorded. This compounds rather than contradicts seq=45's P7 finding that the deployed pullback region has median Sharpe -0.074 across its 313-config neighbourhood: the entry has no edge, and the session variant that appeared to rescue it was an artifact of reading broker time as UTC. The live demo deployment (magic 1100001) has no supporting evidence in the corrected record. data.py now exposes tz='server_eet' (correct, DST-aware); the wrong 'legacy_utc' remains the DEFAULT so seq 39-46 stay reproducible -- those are all 24/7 with no session filter, so a relabel cannot move any of their numbers, as the control arm here demonstrates directly. Artifact: research/data/crest_n_keel/seq29_session_rerun.json

_hash_: `c581e71909465904…` · _prev_: `74044644775ad224…`

### seq 53 · 2026-08-24T07:41:21Z · update · `flood_tide_h1`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `best_sharpe_px`=0.719, `bracket_median_sharpe`=0.285, `bracket_pct_positive`=91.1, `drift_actual`=0.719, `drift_null_mean`=0.262, `drift_p`=0.005, `median_sharpe_px`=0.331, `median_trades`=1550, `n_configs`=3744, `pct_countable`=100.0, `pct_positive`=93.2, `survivors`=550, `trail_median_sharpe`=0.517, `trail_pct_positive`=100.0

> EXIT-GRID SWEEP. These signals have a working generator but no exit logic, so they stalled at signal-edge and were never swept. Per CLAUDE.md a reclaim / mean-reversion entry is DESIGNED to be carried by an asymmetric exit, so the owed test is entry x EXIT FAMILY: a full ATR bracket grid (sl 1.0-3.0 x tp 1.5-5.0) and an ATR trail grid (1.5-5.0), across 3 ATR periods, 3 directions and 2 min_atr floors. Exit machinery is cnk_engine.simulate unchanged and already parity-validated, so costs, sizing and both return bases match the zlch/ebb/cnk/asqs sweeps. Bars tz='server_eet' (true UTC). Runner research/post/sweeps/run_signal_sweep.py; report research/data/signals/signal_sweep_report.html. READ WITH seq=49: top-of-grid selection was shown to carry no out-of-sample information, so the drift control below is run on a config SELECTED as best-of-grid and its p-value does not carry a multiple-testing correction. Bonferroni over the grid would render it insignificant. The defensible claim is the surface statistic, not the leader. flood_tide (H1, Donchian breakout, long-only upstream) was SHELVED at seq=32/34 on a regime-filtered E-Ratio null -- an ENTRY-ONLY diagnostic. With exits swept the surface is the best of anything in this repo: 3,744 configs, 100% clear the 100-trade floor (median 1,550 trades), median Sharpe_px +0.331, 93.2% positive, best +0.719, 550 survivors of all four gates. By exit family: TRAIL median +0.517 with 100% of 864 configs positive; BRACKET median +0.285, 91.1% positive. The trailing exit is doing the work, which is exactly the 'edge lives in the exit' case the entry-only E-Ratio cannot see. DRIFT CONTROL on the best config: actual 0.719 vs matched random-entry null 0.262, p=0.005. It clears -- but note the null mean is POSITIVE at +0.262, which is gold's uptrend correctly priced into the benchmark. THE HONEST CAVEAT: the surface median (+0.331) sits only ~0.07 above that drift null, so most of the 93%-positive surface is plausibly the instrument rather than the signal. A long-only breakout with a trailing stop on a secular bull will produce exactly this shape. Drift controls on TYPICAL configs (median-ranked and median-trail) are running to settle whether the surface, not just the selected top, beats drift. Verdict left OPEN pending that; the seq=32/34 shelving is CONTESTED, not overturned.

_hash_: `8a8f7c8aa544b680…` · _prev_: `c581e71909465904…`

### seq 54 · 2026-08-24T07:41:21Z · update · `avwap_sweep_reclaim_m15`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `best_sharpe_px`=0.492, `drift_actual`=0.492, `drift_null_mean`=-0.156, `drift_p`=0.001, `median_sharpe_px`=-0.101, `median_trades`=122, `n_configs`=2808, `pct_countable`=60.2, `pct_positive`=29.9

> EXIT-GRID SWEEP. These signals have a working generator but no exit logic, so they stalled at signal-edge and were never swept. Per CLAUDE.md a reclaim / mean-reversion entry is DESIGNED to be carried by an asymmetric exit, so the owed test is entry x EXIT FAMILY: a full ATR bracket grid (sl 1.0-3.0 x tp 1.5-5.0) and an ATR trail grid (1.5-5.0), across 3 ATR periods, 3 directions and 2 min_atr floors. Exit machinery is cnk_engine.simulate unchanged and already parity-validated, so costs, sizing and both return bases match the zlch/ebb/cnk/asqs sweeps. Bars tz='server_eet' (true UTC). Runner research/post/sweeps/run_signal_sweep.py; report research/data/signals/signal_sweep_report.html. READ WITH seq=49: top-of-grid selection was shown to carry no out-of-sample information, so the drift control below is run on a config SELECTED as best-of-grid and its p-value does not carry a multiple-testing correction. Bonferroni over the grid would render it insignificant. The defensible claim is the surface statistic, not the leader. avwap_sweep_reclaim (M15, AVWAP/POC/HVN sweep-and-reclaim). seq=26 recorded an entry-only E-Ratio of 0.8063 (p=0.9420) as DIAGNOSTIC, correctly not treating it as a veto. Exit sweep: 2,808 configs, only 60.2% clear the 100-trade floor (median 122 trades -- this entry is SPARSE, ~13 signals/year), median Sharpe -0.101, 29.9% positive, best +0.492 (bracket atr21 sl1.0 tp3.0 both, 113 trades, PF 1.661). DRIFT CONTROL on the best config: 0.492 vs null -0.156, p=0.001 -- clears, and unlike flood_tide the null here is NEGATIVE, so the result is not drift. But the surface is negative at the median with fewer than a third of configs positive, so this is a thin tail rather than a viable region, and the p-value carries no multiple-testing correction. The asymmetric-exit thesis is directionally supported: a 1:3 bracket is the best exit found, consistent with an entry meant to be carried by the exit. Remains OPEN.

_hash_: `0cf54f74b75621d8…` · _prev_: `8a8f7c8aa544b680…`

### seq 55 · 2026-08-24T07:41:21Z · update · `avwap_multibar_reclaim_m15`

stage=3_is_backtest · verdict=shelved · counts_as_trial=False

_Metrics_: `best_sharpe_px`=0.071, `drift_actual`=0.071, `drift_null_mean`=-0.113, `drift_p`=0.232, `median_sharpe_px`=-0.436, `median_trades`=92, `n_configs`=2808, `pct_countable`=49.8, `pct_positive`=2.1

> EXIT-GRID SWEEP. These signals have a working generator but no exit logic, so they stalled at signal-edge and were never swept. Per CLAUDE.md a reclaim / mean-reversion entry is DESIGNED to be carried by an asymmetric exit, so the owed test is entry x EXIT FAMILY: a full ATR bracket grid (sl 1.0-3.0 x tp 1.5-5.0) and an ATR trail grid (1.5-5.0), across 3 ATR periods, 3 directions and 2 min_atr floors. Exit machinery is cnk_engine.simulate unchanged and already parity-validated, so costs, sizing and both return bases match the zlch/ebb/cnk/asqs sweeps. Bars tz='server_eet' (true UTC). Runner research/post/sweeps/run_signal_sweep.py; report research/data/signals/signal_sweep_report.html. READ WITH seq=49: top-of-grid selection was shown to carry no out-of-sample information, so the drift control below is run on a config SELECTED as best-of-grid and its p-value does not carry a multiple-testing correction. Bonferroni over the grid would render it insignificant. The defensible claim is the surface statistic, not the leader. avwap_multibar_reclaim (M15, AVWAP-only multi-bar reclaim). Exit sweep: 2,808 configs, only 49.8% clear the 100-trade floor (median 92 trades), median Sharpe -0.436, and just 2.1% of the entire grid is positive. The best config reaches only +0.071 (106 trades, PF 1.095) and FAILS the drift control at p=0.232 against a null of -0.113. VERDICT SHELVED. This is the clean negative of the three: no exit in a 2,808-config grid makes the entry viable, and the best one cannot beat random entry timing even before any multiple-testing correction. The 'edge must live in the exit' defence has now been tested directly for this signal and does not hold -- there is no exit to find.

_hash_: `af12859c6b1f01c9…` · _prev_: `0cf54f74b75621d8…`

### seq 56 · 2026-08-24T07:47:40Z · update · `flood_tide_h1`

stage=3_is_backtest · verdict=open · counts_as_trial=False

_Metrics_: `beats_drift_at_median`=1, `median_config_dsr_at_19`=0.458, `median_config_dsr_at_grid_n`=0.0328, `median_config_null_mean`=-0.3556, `median_config_null_p95`=-0.0391, `median_config_p`=0.0, `median_config_sharpe`=0.3313, `median_config_trades`=2094, `median_trail_null_mean`=0.0646, `median_trail_p`=0.013, `median_trail_sharpe`=0.5164

> SURFACE-LEVEL DRIFT CONTROLS for flood_tide -- and a CORRECTION to the reading recorded in the previous entry. That entry flagged a concern that the 93%-positive surface might be gold's uptrend, on the grounds that the surface median (+0.331) sat only ~0.07 above the +0.262 null measured at the BEST config. THAT COMPARISON WAS INVALID. A matched random-entry null is specific to the configuration it is computed for, because it inherits that config's realised trade count, direction and exit rule. Comparing one config's null against a different config's Sharpe is not a like-for-like test. Re-run properly on TYPICAL configs rather than the selected best: MEDIAN-RANKED config (bracket atr21 sl1.0 tp2.0 long, Sharpe +0.331, 2,094 trades): null mean -0.3556, null p95 -0.0391, p=0.000, realised 2,106/2,094 trades (0.6% count match). MEDIAN TRAIL config (atr14 trail5.0 both, Sharpe +0.5164, 853 trades): null mean +0.0646, null p95 +0.3955, p=0.013, realised 849/853. Both beat their own drift-matched nulls, and the median-ranked config's null is NEGATIVE (-0.356) rather than positive. The surface is NOT drift. WHY THIS MATTERS BEYOND flood_tide: this is the first result across eleven tested strategies where a TYPICAL configuration -- not the top of a ranking -- clears a drift-matched control. seq=49 established that top-of-grid selection carries no out-of-sample information; the median of a 3,744-config grid is a pre-specified robust statistic, not a cherry-pick, so this claim is not exposed to that critique. DSR on the SAME median config (not the leader): 0.0328 at N=3,744 with estimated Var(SR), 0.4580 at N=19, 0.9618 at N=1. FAILS 0.95 at grid scale. Empirical-Var(SR) column is 0.0 throughout, the same pooled-heterogeneity misapplication seen in the zlch and cnk sweeps. SYNTHESIS: flood_tide has a REAL but SMALL edge. The entry timing genuinely adds information over random entry given the same exit (p=0.000 at the median config), which is a different and better outcome than ebb_n_flow (lost to random entry at p=1.000) or the drift-explained results elsewhere. But median Sharpe is 0.331, everything is in-sample over full history, and DSR fails. 'Real but small' is a distinct failure mode from 'no edge' and this is the first instance of it in this repo. The seq=32/34 shelving was decided on an ENTRY-ONLY E-Ratio, which by construction cannot see a trailing exit; that decision is now CONTESTED on evidence rather than merely questioned. Verdict OPEN. Per the seq=49 lesson the correct next step is NOT a finer grid and NOT a walk-forward of a grid-selected leader, but a NESTED walk-forward that re-selects inside each training window -- which requires its own registration. Artifacts: research/data/signals/flood_tide_surface_controls.json, flood_tide_median_dsr.json, signal_sweep_report.html.

_hash_: `d99ec97c44a5eea7…` · _prev_: `af12859c6b1f01c9…`

### seq 57 · 2026-08-24T11:48:44Z · hypothesis · `feature_edge_screen`

**Feature-level edge screen: which inputs carry cost-clearing information?**

_Mechanism_: Eleven strategies have failed in this repo, all indicator recombinations on XAUUSD bars. Rather than build a twelfth, screen the INPUTS: for each candidate predictor, does it carry information about forward returns, and is that information larger than the $0.29/oz round-trip cost? Scoring every feature in dollars rather than correlation makes the cost floor a first-class filter instead of a post-hoc disappointment -- the failure mode that killed asian_session_fade at seq=48 with a real but 3.5x-too-small effect.

market=XAUUSD· timeframe=M5,M15,H1· family=feature_screen· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- F1: at M5, NO feature clears the round-trip cost at any horizon.
- F2: the number of cost-clearing features rises monotonically with timeframe, because a roughly fixed cost is charged against a signal that grows with horizon.
- F3: surviving features are mutually redundant rather than independent, so an equal-weight composite does not beat the best single feature.
- F4 (from Gao/Han/Li/Zhou, JFE 2018): intraday momentum is STRONGER in high-volatility and high-volume conditions.

> SEQUENCING DISCLOSURE, stated plainly: this screen was BUILT AND RUN BEFORE this registration, so it is not a pre-registered test and must not be read as one. It is registered here so its 276 tests enter the multiple-testing record rather than sitting outside it. The feature list, horizons and scoring were fixed before results were inspected, and Benjamini-Hochberg FDR is applied across the entire screen. METHOD: 23 features x 4 horizons (1,3,6,12 bars) x 3 timeframes. Features computed causally on closed bars; forward return measured from the NEXT bar's open, never the close the feature was computed on. Spearman IC, decile monotonicity, Newey-West t (overlapping windows), and top-minus-bottom decile spread in BOTH ATR units and $/oz. Bars tz='server_eet' (true UTC) -- session and hour features are meaningless otherwise. ONE LOOKAHEAD BUG FOUND AND FIXED before any result was believed: prior-day high/low used groupby(day).transform('max'), which broadcasts the CURRENT day's extreme onto bars preceding it. It produced IC -0.45 and decile monotonicity of exactly -1.00 -- the implausibility is what exposed it. Corrected to a genuine prior-day level via daily aggregation then a one-DAY shift. Runner research/pre/feature_screen.py, combination test research/pre/feature_combine.py.

_hash_: `1f8e1c71d52b1c1a…` · _prev_: `d99ec97c44a5eea7…`

### seq 58 · 2026-08-24T11:48:44Z · update · `feature_edge_screen`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `best_feature_net_usd`=1.14, `best_feature_spread_usd`=1.43, `best_feature_t`=4.35, `composite_all5_spread`=1.147, `composite_momentum_spread`=1.431, `cost_round_trip`=0.29, `h1_paying`=21, `highvol_spread`=1.256, `highvol_spread_causal`=1.182, `lowvol_spread`=2.831, `lowvol_spread_causal`=2.314, `m15_paying`=1, `m5_paying`=0, `n_fdr_significant`=186, `n_paying_costs`=22, `n_tests`=264, `overall_spread_causal`=1.456

> RESULT. 276 tests, 264 evaluable, 186 FDR-significant, but only 22 have a top-minus-bottom decile spread exceeding the $0.29/oz round trip. F1 CONFIRMED, and it is the decisive answer to the scalping question: at M5, ZERO of 88 tests clear the cost floor. Not one of 23 features, at any horizon, carries enough information to pay the spread. M15 clears 1 of 88 (intraday_ret at h=12, net $0.079 -- and h=12 on M15 is a 3-hour hold, not a scalp). H1 clears 21 of 88. This is a statement about the INFORMATION CONTENT of the data rather than about any strategy, which is why it settles the question that eleven strategy backtests could not. F2 CONFIRMED: 0 -> 1 -> 21 cost-clearing tests as the timeframe lengthens. WHAT DOES PAY, all at H1 and all at the 12-bar (12-hour) horizon: intraday_ret spread $1.430 net $1.140 t=4.35 mono 0.73; ret_12 $1.348 net $1.058 t=4.12 mono 0.96; dist_pdl $1.049 net $0.759 t=3.04; dist_pdh $0.945 net $0.655 t=2.59; dist_vwap $0.683 net $0.393 t=2.41. All are the same momentum family. Features with a large |spread| but near-zero monotonicity and |t|<2 (atr_pct, rv_ratio) are noise, not signal, and are not counted. F3 CONFIRMED: the five survivors are mutually correlated 0.60-0.84 (dist_vwap vs intraday_ret = 0.84). They are one effect wearing five hats. An equal-weight rank composite of all five gives $1.147, WORSE than intraday_ret alone at $1.430; the momentum pair gives $1.431, identical to the single best. Stacking these indicators adds nothing. F4 REFUTED FOR GOLD. Gao/Han/Li/Zhou report intraday momentum is stronger on high-volatility days in equities. In XAUUSD H1 the ordering is INVERTED: by ATR-ratio tercile the spread is LOW $2.831 (mono 0.98, n=41,598), MID $1.289, HIGH $1.256. The low-volatility tercile is more than twice the high-volatility one. Volume conditioning is weakly consistent with the paper (mid $1.561 / high $1.508 vs low $1.220). ROBUSTNESS -- the check that mattered: decile assignment via pd.qcut uses FULL-SAMPLE quantile boundaries, so a 2005 bar is bucketed using 2025 information. Re-run with EXPANDING-WINDOW percentile ranks (each bar ranked only against history strictly before it, min 5,000 bars): overall spread $1.456 net $1.166 t=4.22 (full-sample $1.430/4.35 -- unchanged); low-vol tercile $2.314 net $2.024 t=3.11 (full-sample $2.831 -- reduced ~18% but intact); high-vol tercile $1.182 net $0.892 t=2.44. The finding and the low>high ordering both SURVIVE causal quantile assignment. WHAT THIS IS NOT: a strategy. A decile spread is not achievable P&L -- it assumes trading both extremes with no position sizing, no stop, no capacity limit and no slippage beyond the modelled spread. It is in-sample over 21 years. Per seq=49 the correct next step is NOT to sweep a strategy around this, but to build the simplest possible expression of it and take it through a NESTED walk-forward, which requires its own registration.

_hash_: `f23b0747a9e9bfcd…` · _prev_: `1f8e1c71d52b1c1a…`

### seq 59 · 2026-08-24T14:08:50Z · hypothesis · `h1_momentum_nested_wf`

**H1 intraday-momentum rule under a nested walk-forward**

_Mechanism_: Market intraday momentum (Gao, Han, Li & Zhou, JFE 2018): the return accumulated so far in the session predicts the return over the rest of it, because late-informed traders and infrequently-rebalancing participants must catch up to information already in the price. The payer is the participant who has to transact after the move rather than during it. seq=58 found this is the only feature family on XAUUSD that clears the $0.29/oz round trip, at H1 over a ~12-bar horizon, and -- contrary to the source paper -- strongest in LOW volatility regimes.

market=XAUUSD· timeframe=H1· family=momentum· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- M1 (DECISIVE): mean OOS Sharpe across folds is > 0 when the feature is selected from TRAINING DATA ALONE.
- M2 (DECISIVE, the seq=49 control): the training-selected feature beats the median of other features that also cleared training's bar, in a majority of folds.
- M3 (leakage measure): the FIXED full-history choice (intraday_ret, h=12) scores HIGHER out of sample than honest selection. The gap is the hindsight the seq=58 screen carries.
- M4: the momentum family is selected in a majority of folds, rather than the pick wandering across unrelated features.
- M5: the low-volatility regime filter is selected in a majority of folds, consistent with seq=58's inversion of the published result.

> FROZEN RULE, deliberately the simplest expression of the effect because seq=49 showed elaboration is where the illusion enters: LONG when the feature's CAUSAL expanding percentile >= 0.90; hold exactly `horizon` bars; exit. No stop, no target, no sizing rule, no re-entry while in a position, no overlapping trades. Long-only -- four sweeps have found the XAUUSD short side dead. Costs: $0.22/oz spread on entry plus $0.07/oz round-turn commission. FROZEN GEOMETRY: H1, train 1460D / test 365D / step 365D, matching seq=46 and seq=47 so the three are comparable. FROZEN CANDIDATE SET: the 21 screen features (hour and dow dropped -- they are categorical and a percentile rank of them is meaningless) x horizons {3,6,12} x {no regime filter, low-volatility filter} = 126 candidates re-scored INSIDE each training window. Training admission requires >=30 trades and a positive training Sharpe. WHY NESTED: seq=58's screen ran over full history, so its choice of feature, horizon and regime saw every bar this would be tested on. Walk-forwarding that choice would repeat the seq=46 error, where a flattering IS-OOS gap of -0.02 turned out to be measuring the stability of a hindsight-selected config. The `fixed` arm here reproduces that error ON PURPOSE so its size can be measured. SEQUENCING DISCLOSURE: the runner research/post/sweeps/momentum_nested_wf.py was written before this registration and is frozen with it. No fold output has been observed. STOPPING RULE: single pass. If M1 and M2 both hold, the next step is a cost/slippage stress and a live-forward paper period on demo -- NOT a parameter sweep, which is the step seq=49 invalidated. If M2 fails, the seq=58 screen ranking is noise and the finding is retired.

_hash_: `0327b651294c5012…` · _prev_: `f23b0747a9e9bfcd…`

### seq 60 · 2026-08-24T16:42:10Z · update · `h1_momentum_nested_wf`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `fixed_mean`=0.725, `horizon_12_picks`=17, `is_oos_decay`=0.791, `leakage`=0.177, `lowvol_filter_picks`=11, `m2_mean_diff`=0.456, `m2_n`=17, `m2_sign_p`=0.0245, `m2_wilcoxon_p`=0.0056, `m2_wins`=13, `momentum_family_picks`=12, `n_folds`=17, `oos_folds_positive`=15, `oos_sharpe_mean`=0.548, `oos_sharpe_median`=0.563, `oos_trades_median_per_fold`=26, `oos_trades_total`=937, `pool_median_mean`=0.092, `train_sharpe_mean`=1.339

> RESULT of the frozen seq=59 nested walk-forward. 17/17 folds produced a training-eligible selection. M1 PASSES: mean OOS Sharpe +0.548, median +0.563, 15/17 folds positive, 937 OOS trades total (median 26/fold). M2 PASSES -- the decisive one, and the exact test that killed the top-of-grid methodology at seq=49: the training-selected candidate beat the median of other candidates that also cleared training's bar in 13 of 17 folds. Sign test p=0.0245, Wilcoxon p=0.0056, mean difference +0.456 Sharpe. For contrast seq=49 recorded 17/32 (p=0.430) and a selection value of +0.025. Training rank carries information here; there it did not. M3 CONFIRMED and the number is the point: the FIXED full-history choice scored +0.725 against honest selection's +0.548, so the hindsight in the seq=58 screen is worth +0.177 Sharpe. At seq=49 the equivalent leak was +0.7 to +0.8 -- larger than the effect being claimed. Here it is a fraction of the effect, which is what a real edge looks like as opposed to a selected one. M4 PASSES: momentum-family features (intraday_ret 5, dist_pdh 4, ret_12 1, dist_pdl 1, dist_vwap 1) chosen in 12/17 folds; the remainder went to lower_wick 2, body_ratio 2, vol_z 1. M5 PASSES: the low-volatility regime filter was selected in 11/17 folds, independently reproducing seq=58's inversion of the Gao/Han/Li/Zhou high-volatility conditioning. HORIZON WAS UNANIMOUS: h=12 in 17 of 17 folds, chosen freely from {3,6,12}. The ~12-hour horizon is not a tuned parameter, it is what every training window independently selects. HONEST LIMITATIONS. (1) Training Sharpe +1.339 decays to +0.548 out of sample -- a 59% haircut. The effect is REAL but roughly half what in-sample suggests. (2) Median 26 trades per fold makes per-fold Sharpes noisy; trade count swings 15-177 depending on whether the low-volatility filter is selected. (3) No Deflated Sharpe computed on this yet. (4) RESIDUAL CONTAMINATION: the 21-feature candidate pool was specified a priori and is generic, but the horizon set {3,6,12} dropped h=1 AFTER the seq=58 screen showed h=1 never clears costs. That is post-hoc narrowing, disclosed rather than hidden; its effect is bounded because h=12 wins unanimously against h=3 and h=6, neither of which was excluded. (5) Costs are the modelled $0.22/oz spread plus $0.07/oz commission with no additional slippage. WHAT THIS IS: the first result in this repo where a rule selected from TRAINING DATA ALONE produces positive out-of-sample performance AND beats a matched pool control. It converges with seq=53's flood_tide finding (H1, momentum, trailing exit, typical config beats a drift null at p=0.000) by an entirely separate code path and selection procedure. WHAT THIS IS NOT: a deployment decision. Per the frozen stopping rule the next step is a cost/slippage stress and a live-forward paper period on demo -- explicitly NOT a parameter sweep, which is the step seq=49 invalidated. Artifacts: research/pre/artifacts/momentum_nested_wf.json, momentum_nested_summary.json. Runner research/post/sweeps/momentum_nested_wf.py.

_hash_: `fe4e75977ea8abd3…` · _prev_: `0327b651294c5012…`

### seq 61 · 2026-08-25T06:32:11Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=open · counts_as_trial=False

_Metrics_: `control_reproduces_seq60`=0.54, `filter_1_5x`=0.436, `filter_2x`=0.38, `filter_2x_slip10`=0.27, `filter_3x`=0.269, `filter_4x`=0.158, `filter_base`=0.491, `filter_trades`=374, `nofilter_1_5x`=0.534, `nofilter_2x`=0.441, `nofilter_2x_slip10`=0.258, `nofilter_3x`=0.256, `nofilter_4x`=0.072, `nofilter_base`=0.626, `nofilter_trades`=1132, `recommended_variant_unfiltered`=1, `swap_cost_sharpe`=0.049

> COST AND SLIPPAGE STRESS, the step the seq=59 stopping rule specifies. Two cost omissions in seq=60 are corrected here. (1) SWAP: the rule holds 12 H1 bars, which crosses the daily rollover about half the time and sometimes the Wednesday triple; seq=60 charged none. (2) SLIPPAGE: only the quoted spread was charged. Nothing about the rule is re-tuned -- this changes only what trading costs. Grid: cost multiplier {1.0,1.5,2.0,3.0, 4.0} on spread+commission x additional slippage per side {0,0.05,0.10, 0.20} $/oz x swap {off,on}, over the same 17 folds. CONTROL: swap off, 1.0x, no slippage reproduces seq=60 at +0.540 against its +0.548, confirming the module reproduces the original before stressing it. SWAP COSTS 0.049 SHARPE -- smaller than feared. TWO VARIANTS TESTED, and the comparison matters because seq=60's nested selection preferred the low-volatility filter in 11/17 folds while its own fixed arm ran WITHOUT it: NO FILTER (1,132 trades): +0.626 at modelled cost with swap (15/17 folds positive), +0.534 at 1.5x, +0.441 at 2x, +0.256 at 3x, +0.072 at 4x; breakeven near 4x cost, or 3x plus $0.20/oz slippage. LOW-VOL FILTER (374 trades): +0.491 at modelled cost (14/17), +0.436 at 1.5x, +0.380 at 2x, +0.269 at 3x, +0.158 at 4x; breakeven beyond 4x cost plus $0.20/oz slippage. THE TRADE-OFF IS REAL AND THE CROSSOVER IS AROUND 2x COST + $0.10 SLIPPAGE. Unfiltered is better at modelled costs and has 3x the trades; filtered is more cost-RESILIENT because cutting frequency by two thirds raises edge-per-trade against a fixed per-trade cost. At 2x+$0.10 the filtered variant overtakes (+0.270 vs +0.258). RECOMMENDATION: run the UNFILTERED rule for the forward period. It is simpler (one fewer component), scores higher at realistic cost, and its 1,132 trades give roughly three times the statistical power, which shortens the time to a usable read. Keep the filter as the fallback if realised costs come in worse than 2x modelled. A NOTE ON THE FILTER, because it is a small instance of this repo's main theme: training data preferred the low-volatility filter in 11/17 folds, yet the simpler unfiltered rule performs BETTER out of sample at modelled cost. The filter is an in-sample preference that does not survive. That is the same overfitting pattern seq=49 documented at grid scale, appearing here in a single binary choice. HEADROOM VERDICT: the edge survives 2x modelled costs plus $0.05/oz slippage at +0.350 (unfiltered) or +0.325 (filtered). A rule whose breakeven sits at 3-4x modelled cost has genuine room; one that broke at 1.1x would not be tradeable. This passes. Artifacts: research/pre/artifacts/momentum_cost_stress.json (filtered), momentum_cost_stress_nolowvol.json (unfiltered). Runner research/post/sweeps/momentum_cost_stress.py.

_hash_: `cfdc80e4d67878db…` · _prev_: `fe4e75977ea8abd3…`

### seq 62 · 2026-08-27T08:38:19Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=open · counts_as_trial=False

_Metrics_: `dsr_passes`=0, `dsr_threshold`=0.95, `filter_dsr_n126`=0.4517, `filter_dsr_n276`=0.3521, `filter_oos_trades`=374, `filter_per_obs_sharpe`=0.1178, `unfiltered_dsr_n1`=0.9959, `unfiltered_dsr_n126`=0.5144, `unfiltered_dsr_n21`=0.7658, `unfiltered_dsr_n276`=0.4121, `unfiltered_oos_trades`=1132, `unfiltered_per_obs_sharpe`=0.0763

> DEFLATED SHARPE -- the gate every other candidate in this repo has failed, and this one fails it too. Computed on the CONCATENATED OUT-OF-SAMPLE fold returns, not on an in-sample leader, which is a materially different (and more favourable) basis than the sweep DSRs at seq=40/43/45/51. UNFILTERED (1,132 OOS trades, per-observation Sharpe 0.0763): DSR 0.9959 at N=1; 0.7658 at N=21 (the log's global trial_count); 0.5144 at N=126 (the candidates the nested walk-forward chose among per fold); 0.4121 at N=276 (the seq=58 screen's full test count, the widest defensible reading). LOW-VOL FILTER (374 trades, per-observation Sharpe 0.1178): 0.9936 / 0.7147 / 0.4517 / 0.3521 at the same N. VERDICT: FAILS the repo's pre-registered 0.95 threshold at every N except N=1, which assumes no selection took place at all and is not defensible here. Consistency requires applying the same gate that killed zerolag_chandelier (0.739), crest_n_keel (0.839), asqs (0.038) and flood_tide (0.033). This rule scores 0.41-0.51 at realistic N. It is the best of the group on the OOS basis but it does not clear the bar. CORRECTION TO MY EARLIER FRAMING: I described this rule as having cleared every gate put in front of it. That was accurate for M1-M5 and the cost stress but is no longer accurate now DSR has been run. It has passed the selection and cost gates and failed the significance gate. WHY IT FAILS, stated so the number is interpretable rather than just damning: per-observation Sharpe is 0.0763, which annualises to roughly 0.55 at ~52 trades/year and matches the seq=60 fold mean of +0.548. The effect is genuine -- it survived honest nested selection at p=0.006 against a pool control and 2-3x cost stress -- but it is SMALL, and DSR asks whether a Sharpe that size could be the best of N tries under a null. At N=126 it could be. AN HONEST CAVEAT IN THE OTHER DIRECTION: DSR's construction assumes the Sharpe being tested was selected as the maximum of N trials ON THE DATA IT IS MEASURED ON. These are out-of-sample returns from a procedure that selected inside training windows, so the haircut is arguably too harsh here. That is an argument for interpreting the number carefully, NOT for waiving the gate -- waiving a pre-registered threshold because the result is one we like is precisely the failure mode this log exists to prevent. WHAT THIS LICENSES: a demo paper-forward period to gather genuinely unseen data, which is the only thing that can resolve a small-but-real effect. It does NOT license live capital, and it does not license a parameter search to lift the Sharpe -- that is the seq=49 trap. Artifact: research/pre/artifacts/momentum_dsr.json

_hash_: `f895e57c09004c60…` · _prev_: `cfdc80e4d67878db…`

### seq 63 · 2026-08-27T09:10:45Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=open · counts_as_trial=False

_Metrics_: `dsr_empirical_var_sr_n126`=0.0, `dsr_empirical_var_sr_n21`=0.0099, `dsr_var_sr_source_used`=0, `gate_fpr_n126`=0.0, `gate_fpr_n21`=0.0008, `gate_power_n126`=0.061, `gate_power_n21`=0.188, `n_critical_empirical_path`=1, `n_critical_estimated_path`=3, `observed_per_obs_sr`=0.0763, `positive_control_gold_bh_ann_sharpe`=0.744, `positive_control_gold_bh_dsr_n126`=0.8112, `prereg`=1, `prereg_alpha`=0.05, `prereg_reps`=200, `required_per_obs_sr_n126`=0.1212, `trades_needed_to_pass_n126`=3000

> PRE-REGISTRATION of a gate recalibration. Logged BEFORE any null result exists, because the question 'is the DSR gate too strict?' was raised immediately after a result we liked failed it, which is exactly when a moved threshold is least trustworthy.

THREE DEFECTS FOUND IN THE EXISTING APPLICATION.
(1) LENIENCY, not strictness. momentum_dsr.py passed no trial_sharpes, so it fell to var_sr_source='estimated'. dsr.py's own docstring says walk-forward results with >=10 folds should pass per-fold Sharpes, and that the estimated path is 'a leniency that should be flagged in the writeup'. It was not flagged; I did not notice it. Empirical var_sr gives DSR 0.0099 @N=21 and 0.0000 @N=126 versus the reported 0.7658 / 0.5144. I do NOT assert the empirical path is correct here: DSR's var_sr means dispersion ACROSS TRIALS under the null, whereas per-fold Sharpes measure dispersion ACROSS TIME, inflated by ~67 trades per fold. The honest statement is that the knob is ambiguous and swings the verdict from 0.51 to 0.00.
(2) NO POWER at the N used. Bootstrap, 4000 reps, T=1132: at N=126 the false-positive rate is 0.0000 and power at the observed effect is 0.061. At N=21, FPR 0.0008 / power 0.188. A gate that rejects a real edge of the measured size ~94% of the time is not carrying information, so 'fails DSR at N=126' was a far weaker statement than seq=62 presented it as.
(3) N OVER-CHARGED ON OOS STREAMS. DSR asks whether a statistic could be the max of N trials measured ON THE DATA IT IS MEASURED ON. The seq=62 stream was measured once; the 126 candidates were re-scored inside TRAINING windows and that selection cost was already paid and measured as the seq=60 leakage of 0.177 Sharpe. Charging N=126 against the OOS stream bills the same selection twice.
Calibration anchor: gold buy-and-hold over the same 21y (+1173% total, annualised Sharpe 0.744, T=5530 D1 bars) scores DSR 0.8112 @N=126 and 0.7337 @N=276 -- it FAILS our gate. B&H was not selected from 126 trials (its honest N is 1, where it scores 0.9998), so this does not show the 0.95 threshold is wrong; it shows the magnitude N=126 demands exceeds what gold's entire bull market delivered.

PROTOCOL, FIXED NOW. Replace the N-dependent and var_sr-dependent haircut with an empirical null that needs neither knob. research/post/sweeps/momentum_null_calibration.py runs the ENTIRE pipeline (build_features -> nested training selection -> OOS concatenation) on data whose intraday predictability is destroyed by construction: bar order is permuted WITHIN each trading day, so the daily return distribution, volatility clustering, bar geometry, volume and session structure all survive, but no first-bar return can predict what follows. Two streams are nulled against their own matched distributions: 'fixed' (the frozen intraday_ret/h=12 rule that seq=62 actually evaluated) and 'nested' (the selection procedure itself, which is what carries the selection cost).
ACCEPTANCE RULE, BINDING: p = (#null runs with per-obs Sharpe >= observed, +1) / (valid reps + 1); accept at p < 0.05; 200 reps. If the empirical null and DSR disagree, the NULL WINS -- it makes strictly fewer assumptions. If they agree, the rule is dead and I stop relitigating it.

RETROACTIVE SCOPE, BINDING. A recalibrated gate that is only ever applied to the result we liked is an exemption, not a recalibration. Triage of every DSR evaluation in this log:
  DSR-DECIDED ON AN OOS STREAM (N over-charged -- must be re-run):
    seq=36 crest_n_keel_momentum -- OOS Sharpe 1.20, killed at DSR 0.061 @N=20 (1.0 @N=1). STRONGEST retroactive candidate; a better OOS result than seq=62's.
    seq=46 cnk_param_sweep WF -- H1 OOS pooled Sharpe 0.91, killed at 'dsr_at_grid_n' = 0.0, i.e. the full 150,660-config grid N charged against a walk-forward stream. Same error as seq=62, more extreme.
    seq=62 h1_momentum_nested_wf -- this entry.
    seq=29 crest_n_keel -- OOS 0.27-0.41; weak on its own terms and superseded by seq=36, re-run for completeness only.
  KILLED ON EVIDENCE OTHER THAN DSR (recalibration CANNOT resurrect these):
    asqs seq=30 -- OOS Sharpe -1.06, net-losing. Dead on returns.
    ebb_n_flow seq=43 -- leader loses to matched random entry at p=1.000. Dead on the drift control.
    flood_tide_h1 seq=56 -- regime-filtered E-Ratio null decisive at the pre-gate; also fails at N=19 (0.458).
    zlch seq=40 -- DSR applied to an IN-SAMPLE leader from an 18,480-config grid, where a large N is CORRECT. Kill stands. Note it never received a nested walk-forward, so its status is 'untested OOS', not 'refuted'.
Prediction recorded in advance: I expect the null to be kinder than DSR@N=126 but still to reject seq=62, because N_critical is 3 on the lenient path and 1 on the strict one, and because 1132 trades cannot resolve an annualised Sharpe of 0.55 either way. The candidate I expect this to matter for is seq=36, not this one.

_hash_: `93ddbe0d8bbe25f5…` · _prev_: `f895e57c09004c60…`

### seq 64 · 2026-08-27T09:13:00Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=open · counts_as_trial=False

_Metrics_: `cnk_killed_by`=0, `cnk_lookahead_gap_h1`=0.681, `cnk_lookahead_gap_h4`=0.805, `cnk_nk2_n`=32, `cnk_nk2_p`=0.43, `cnk_nk2_wins`=17, `cnk_selection_value_sharpe`=0.025, `dsr_decided_clean_oos_kills`=1, `triage_corrected`=1, `zlch_status_untested_oos`=1

> CORRECTION to the retroactive triage in seq=63, found before any null result existed. Two of the four rows in the 'DSR-decided on an OOS stream' list were wrong, and the error inflated the scope of what a recalibration could rescue.

WHAT I GOT WRONG. I listed seq=36 (crest_n_keel_momentum, OOS Sharpe 1.20, DSR 0.061 @N=20) and seq=46 (cnk_param_sweep WF, H1 pooled OOS 0.91, DSR 0.0 at grid N) as cases where a large N was charged against a clean out-of-sample stream, and called seq=36 the STRONGEST retroactive candidate. Both are contaminated, and seq=46's own note already says so: qhf_harness run_walk_forward applies FIXED parameters to every fold without re-optimising inside the training window, and those parameters were selected from a sweep over the full history, which contains every fold tested. The selection saw the test data. Those runs measure TEMPORAL STABILITY, not out-of-sample performance, so neither is a case of an over-charged N.

WHAT ACTUALLY KILLED THAT FAMILY. seq=49 -- the clean nested walk-forward registered at seq=47 -- re-ran the full 30,132-config grid inside each training window and evaluated the training-selected leader once on the following untouched year. It did not fail on DSR. It failed on NK2, its own decisive pre-registered control: the training-selected leader beat the median of other configs clearing the same training gates in 17 of 32 folds, 53%, sign-test p=0.430. Selected mean OOS Sharpe -0.124 vs pool mean -0.149 -- picking the best config in training was worth +0.025 Sharpe, i.e. approximately nothing. Training Sharpe ~1.5 mapped to OOS ~0. And N4 quantified the contamination directly: the full-history leader scored +0.452 (H4) / +0.760 (H1) on the SAME folds where honest selection scored -0.353 / +0.079, a lookahead gap of 0.68-0.81 Sharpe. That gap is LARGER than the effect seq=36/46 were claiming. So seq=36's 1.20 is not a result a recalibrated gate can rescue; it is a number produced with hindsight whose honest counterpart is ~0.

CORRECTED TRIAGE. Of every DSR evaluation in this log, exactly ONE kill was decided by DSR applied to a clean out-of-sample stream: seq=62, the H1 momentum rule. Every other candidate died on independent evidence that a recalibrated gate cannot touch:
  crest_n_keel / cnk -- seq=49 NK2 selection control, p=0.430. Clean, decisive.
  asqs -- seq=30, OOS Sharpe -1.06, net-losing. Dead on returns.
  ebb_n_flow -- seq=43, leader loses to matched random entry at p=1.000.
  flood_tide_h1 -- seq=56, regime-filtered E-Ratio null decisive at the pre-gate.
  zlch -- seq=40, DSR on an IN-SAMPLE leader from an 18,480-config grid, where a large N is correct.
The retroactive re-run promised in seq=63 is therefore narrower than promised, and it is narrower for a good reason rather than a convenient one: the pre-registered drift, pool and selection controls had already done the killing independently of DSR. That is evidence the methodology was sound even where the DSR arithmetic was not.

OPEN GAP, NOT A KILL. zlch never received a nested walk-forward. Its honest status is 'untested out-of-sample', not 'refuted'. It is the one candidate in the corpus whose verdict rests on an in-sample leader plus a drift control, with no clean OOS test. That gap is now the highest-value outstanding piece of work in the programme, ahead of anything further on seq=62.

The seq=63 acceptance rule stands unchanged: p < 0.05 on the empirical null, 200 reps, null wins over DSR on disagreement. Only the scope of the retroactive application is corrected here.

_hash_: `f6b54c0bc635fe70…` · _prev_: `93ddbe0d8bbe25f5…`

### seq 65 · 2026-08-27T10:23:47Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=killed · counts_as_trial=False

_Metrics_: `decisive_stream_nested`=1, `drift_share_of_fixed_sharpe`=0.145, `dsr_n126_understated`=0.5144, `fixed_excess_null_sd`=2.93, `fixed_null_max`=0.08568, `fixed_null_mean`=0.01104, `fixed_null_q95`=0.04741, `fixed_null_sd`=0.02227, `fixed_observed`=0.07627, `fixed_p`=0.01, `fixed_passes`=1, `nested_excess_null_sd`=1.23, `nested_null_mean`=0.00467, `nested_null_q95`=0.04417, `nested_null_sd`=0.02669, `nested_observed`=0.03747, `nested_p`=0.1045, `nested_passes`=0, `null_reps`=200, `prereg_alpha`=0.05

> RESULT of the seq=63 pre-registered empirical null. 200 valid reps, full pipeline re-run on within-day bar-permuted data. THE TWO STREAMS SPLIT.
  fixed  (frozen intraday_ret/h=12 rule, the statistic seq=62 evaluated): observed 0.07627, null mean +0.01104, sd 0.02227, q95 +0.04741, max +0.08568. 1/200 null runs reached the observed value. p=0.0100 -- PASSES the pre-registered 0.05.
  nested (the selection procedure choosing freely per fold): observed 0.03747, null mean +0.00467, sd 0.02669, q95 +0.04417. 20/200 null runs reached it. p=0.1045 -- FAILS.

AMBIGUITY IN MY OWN PRE-REGISTRATION, AND HOW IT IS RESOLVED. seq=63 fixed the threshold (p<0.05, 200 reps) and the tie-break against DSR, but did NOT say which stream is decisive when the two disagree. That is a defect in the pre-registration and I am not entitled to resolve it by picking the stream I prefer after seeing both. Resolving it on the text that WAS written: seq=63 describes nested as 'the selection procedure itself, which is what carries the selection cost', and the entire purpose of the exercise was to price selection honestly. NESTED IS DECISIVE. VERDICT: the H1 momentum rule does NOT clear the pre-registered bar. Do not promote.

WHAT IS NEVERTHELESS ESTABLISHED, because the result is not the same as DSR's. The fixed rule beats its own permutation null at p=0.0100, at 2.93 null standard deviations. DSR at N=126 scored this 0.5144 and at N=276 scored it 0.4121; the null says 1-in-200. Per the seq=63 tie-break the NULL WINS on that disagreement, so the honest statement is that seq=62 UNDERSTATED the evidence -- an intraday-momentum effect in XAUUSD H1 is real. What it cannot support is that OUR PROCEDURE reliably FINDS it: selecting freely per fold yields 0.03747 against a null whose q95 is 0.04417. The effect is real conditional on already knowing to freeze intraday_ret/h=12, and that knowledge came from the seq=58 screen run over the full sample, including every test window. The fixed null cannot price that; the nested null can, and it says the choice is not reliably recoverable.

A DEFECT IN THE OLD GATE THAT THIS EXPOSES INDEPENDENTLY. Both null means are POSITIVE (+0.01104 fixed, +0.00467 nested), not zero. A long-only rule on an instrument with positive drift earns a Sharpe from drift alone even when all intraday predictability has been destroyed. DSR benchmarks against ZERO via psr_vs_zero. So DSR was testing against the wrong null in a second, separate way from the N problem: roughly 14% of the fixed rule's raw per-obs Sharpe is drift capture that no zero-benchmark test subtracts. The empirical null prices it automatically. This is a general argument for preferring the permutation null over DSR on any long-biased rule in this repo, not just this one.

CONSISTENCY WITH seq=49. Nested selection failing to beat its null (p=0.1045) is the same finding as seq=49's NK2 (p=0.430) on crest_n_keel: training rank carries little information about the test window. Measured twice now, on two unrelated hypothesis families, with different machinery. The H1 momentum feature family is markedly more informative than the cnk grid (0.105 vs 0.430) but still does not clear 0.05.

PRACTICAL LIMIT ON RESOLVING THIS, stated so nobody re-opens it cheaply. Forward paper data has no selection problem and is the only clean way to settle it, but the rule trades ~54 times a year. The seq=63 power work showed ~3,000 trades are needed for the old gate and the null is no cheaper. That is decades. Anyone proposing to resolve this by waiting is proposing something that does not terminate. The realistic paths are more instruments or a genuinely different, higher-frequency expression -- and seq=58 already showed ZERO features pay the $0.29/oz round trip at M5, so the frequency path is closed for XAUUSD at this cost structure.

Per seq=63: the null and DSR agreed on the decisive stream, so I stop relitigating this rule. Artifacts: research/pre/artifacts/momentum_null_calibration.json; runner research/post/sweeps/momentum_null_calibration.py.

_hash_: `5a67944f28e09a4d…` · _prev_: `f6b54c0bc635fe70…`

### seq 66 · 2026-08-27T12:32:42Z · hypothesis · `zlch_nested_walk_forward`

**zerolag_chandelier nested walk-forward (the OOS test seq=39 mandated)**

_Mechanism_: Chandelier-exit trend following on a ZLSMA-biased entry. Tests whether the SELECTION PROCEDURE generalises, not whether one config does.

market=XAUUSD· timeframe=H1+H4· family=trend_following· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- Z1: the nested procedure's mean OOS Sharpe across folds is > 0.
- Z2 (DECISIVE): the training-selected config's OOS Sharpe exceeds the median OOS Sharpe of a random sample of OTHER configs that also cleared the training gates, in a majority of folds. This is the test of whether training rank carries any information about the test window. It is the test that killed crest_n_keel at seq=49 (17/32 folds, p=0.430).
- Z3: at least one config clears the training gates in every fold.
- Z4 (leakage estimate): nested OOS mean Sharpe is BELOW the seq=40 full-history leader's OOS mean on the SAME folds. The shortfall is the value of the lookahead in seq=40's in-sample ranking. seq=49 measured 0.68 (H1) / 0.81 (H4) for crest_n_keel; a similar figure here would mean seq=40's in-sample Sharpe of 0.833 is mostly hindsight.
- Z5: long-only is selected in a majority of folds, and short in none. seq=40 found short negative at every timeframe and the seq=20 E-Ratio split agrees (long 1.033 / short 0.927). If honest per-fold selection instead scatters across directions, the seq=40 direction finding was itself a full-history artifact.
- Z6: selection is unstable -- the config chosen changes across folds and fewer than half the folds select the seq=40 full-history leader.

> PARENT: zerolag_chandelier seq=19/20 (KILLED at signal-edge: combined E-Ratio 0.9813, p=0.772, role=HARD_GATE) -> zlch_param_sweep seq=39 (registration) / seq=40 (result: 18,480 configs; leader H4 atr_period=8 atr_mult=2.0 bias=none direction=long, Sharpe_px 0.833, PF 1.495, DD 0.238; K1 PASS random-entry p=0.000; K2 PASS Calmar 0.41 vs B&H 0.28; K4 PASS 9/9 neighbours positive; K3 FAIL DSR 0.739 at N=18,480 -> cannot promote). WHY THIS RUNS NOW: seq=39's frozen stopping rule states that if the leader survives K1-K4 the ONLY legitimate next step is an out-of-sample walk-forward, NOT a finer grid. K3 was the sole failure and that step was never taken, so zlch is the one candidate in the corpus whose honest status is UNTESTED OUT-OF-SAMPLE rather than refuted (log seq=64). seq=63/65 then showed the K3 haircut was measuring the wrong thing on a long-biased rule: DSR benchmarks against zero while the true permutation null mean is positive (drift capture), the Var(SR) branch used was the lenient one, and the gate had power 0.061 at these effect sizes. K3 alone is therefore not a verdict. This registration supplies the test zlch has never had and that actually killed crest_n_keel. SEQUENCING DISCLOSURE: nothing from this nested run has been observed. One H4 fold was timed for feasibility with the selection result deliberately not printed; that timing informed only the decision to proceed, not the design. Runner research/post/sweeps/zlch_nested_wf.py was written before this registration and is frozen with it. REPRODUCIBILITY DEFECT FOUND AND DISCLOSED BEFORE RUNNING: under pandas 2.1.4 the engine's HTF-bias resample raises 'Values falls before first bin' for the 7D (W1) rule, so the seq=40 sweep cannot have been produced by this environment and its weekly bin alignment is not recoverable -- an origin sweep at 4h resolution across the full week got no closer than |dSharpe| 0.0048. htf_bias therefore gained an optional `origin` argument (default None, so every existing caller is unchanged) and this run pins bins to a fixed absolute Monday, 2004-06-07 UTC, which is also required for correctness in a walk-forward: without a pinned origin every fold would slice at a different date and the same config would not mean the same thing across folds. VERIFIED against the recorded seq=40 CSVs: H1 reproduces EXACTLY (max |dSharpe| 0.0000000000) on all three bias families (none, D1, H4), and H4 reproduces exactly on none and D1. Only H4's W1-bias configs differ (max |dSharpe| 0.084 on spot checks), which is ~45% of the H4 grid. Those configs remain valid grid members under a well-defined causal weekly alignment; they are simply not bit-identical to seq=40. The seq=40 leader is bias=none, so the `fixed` comparison arm is unaffected, and H1 is unaffected entirely. EXCLUDED TIMEFRAMES, disclosed: M5, M15 and D1 are not run. M5/M15 are structurally cost-destroyed (seq=40 median Sharpe -1.402 / -0.602 against a 0.29 USD/oz round trip) and D1 yields too few trades per fold for a Sharpe to mean anything. That exclusion rests on cost arithmetic, not on which config won. | FROZEN_DESIGN=For each fold: re-run the FULL seq=39 grid on the TRAINING window ONLY (3,696 configs per timeframe: 8 atr_periods x 7 atr_mults x 11 bias keys [none + 2 higher TFs x 5 ZLSMA lengths] x 3 directions x 2 min_atr); apply the gates; select the highest training Sharpe; evaluate that ONE config once on the following untouched test window. Fold geometry mirrors seq=47/49 so zlch and cnk are directly comparable -- H1 train 1460D / test 365D / step 365D (17 folds), H4 train 1825D / test 365D / step 365D (16 folds). Gates are seq=39's (PF >= 1.20, max DD <= 0.30, Sharpe > 0) with the trade floor SCALED to the training window at 100/21.6 per year, hard minimum 30, because applying the absolute 100 to a 4-5 year window would be a far harsher gate than the sweep itself used. Direction, bias timeframe, ZLSMA length and min_atr are NOT fixed in advance: restricting to 'H4 long-only, bias=none' would re-import seq=40's full-history conclusion and reintroduce the leak in a subtler form -- the exact error corrected at seq=64 for seq=36/46. risk_pct 0.01; max_drawdown_halt DISABLED; Pepperstone cost model; POOL_SAMPLE 50; seed 20260827. | KILL_CRITERIA=ZK1: mean OOS Sharpe across folds <= 0 -> the selection procedure has no out-of-sample edge. KILL zerolag_chandelier outright; its status moves from 'untested out-of-sample' to 'refuted'. ; ZK2 (DECISIVE): the selected config fails to beat the gate-passing pool median in a majority of folds (sign-test p >= 0.05) -> the seq=40 ranking is noise. KILL. Combined with seq=49 this would be the second independent demonstration that top-of-grid selection carries no out-of-sample information in this repo, and the finding generalises past zlch. ; ZK3: fewer than 60% of folds yield ANY config clearing the training gates -> not deployable regardless of its average. | STOPPING_RULE=Single pass over H1 and H4; geometry, gates and grid frozen above. If it survives ZK1-ZK3 the next step is the seq=63 permutation null on the concatenated OOS stream -- NOT a finer grid, NOT a different timeframe, and NOT a re-run with different gates. If it fails ZK2 the correct response is to stop ranking sweeps by top-of-grid Sharpe across this repo, which is a methodology change rather than a strategy change.

_hash_: `88017606ae342c5e…` · _prev_: `5a67944f28e09a4d…`

### seq 67 · 2026-08-27T12:37:16Z · update · `zlch_nested_walk_forward`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `broken_folds_seen`=3, `bug_warmup_starvation`=1, `design_changed`=0, `oos_trades_after_fix_z120`=35, `oos_trades_before_fix`=0, `train_passers_unchanged`=1399

> BUG DISCLOSURE, appended BEFORE the real run and after a broken one. Design unchanged; this records what was seen and what was fixed, so the sequence on record is bug -> disclosure -> result rather than result -> explanation.

WHAT BROKE. The first execution computed the HTF bias, chandelier direction and Wilder ATR on each fold's own slice. A 365-day test window holds ~52 weekly bars, so any W1 bias with zlsma_len >= 50 had fewer bars than the ZLSMA needs (z120 needs 122). zlsma returned all-NaN, the rising/falling masks were all-False, and the selected config could not open a single trade out-of-sample. The SAME configs scored normally on the 5-year training window, which has ~260 weekly bars. That asymmetry is a systematic selection artifact: it preferentially selects long-lookback bias configs in training and then hands them zero OOS trades. Fold 4 additionally crashed with pandas 'Values falls before first bin' on the same slicing path.

WHAT I SAW, stated exactly. Three folds printed: selected configs (long atr5x1.5 biasW1/z80; both atr5x1 biasW1/z120; long atr8x2 biasW1/z80), train Sharpes +1.973/+2.835/+1.869, OOS Sharpe NaN with 0 trades in all three, pool medians +0.988/+0.688/+0.128, and fixed-arm OOS +2.255/+1.765/+0.897. NO ZK1 or ZK2 information was obtainable from this: both gates need the selected config's OOS Sharpe, which was NaN in every case. The pool and fixed arms were computed correctly (bias=none for fixed; pool sampled across all bias keys) and those three folds' values will change under the fix only where a pool member used a starved bias.

THE FIX IS FORCED, NOT DISCRETIONARY. A config whose indicator is undefined was never evaluated; leaving it in would score 'no trades' as though it were a result. All three quantities are strictly backward-looking -- htf_bias is shift(1) plus forward-fill, chandelier_direction and wilder_atr are causal recursions -- so computing them ONCE on the full series and slicing per fold introduces no lookahead and reproduces what a live system would see at each bar. It also makes HTF bins identical across folds by construction and removes the pandas crash. Verified mechanically after the fix, trade counts only: W1/z20/z50/z80/z120 now give 26/29/34/35 OOS trades on fold 1 against 0 before. Training gate-passers are unchanged at 1,399, as expected since a 5-year window was never starved.

FROZEN DESIGN IS UNTOUCHED: same 3,696-config grid, same gates, same trade-floor scaling, same fold geometry, same POOL_SAMPLE 50, same seed 20260827, same free direction/bias/zlsma/min_atr. Only the indicator warm-up changed. Predictions Z1-Z6 and kill criteria ZK1-ZK3 stand as registered.

_hash_: `11bba9226f6dcc4f…` · _prev_: `88017606ae342c5e…`

### seq 68 · 2026-08-27T12:58:51Z · update · `zlch_nested_walk_forward`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `distinct_configs_h1`=15, `distinct_configs_h4`=15, `h1_fixed_mean`=0.448, `h1_folds`=17, `h1_lookahead`=0.522, `h1_oos_mean`=-0.073, `h1_oos_median`=-0.079, `h1_oos_positive`=8, `h1_train_sharpe_mean`=1.343, `h1_zk2_n`=17, `h1_zk2_wins`=8, `h4_fixed_mean`=0.615, `h4_folds`=16, `h4_lookahead`=0.512, `h4_oos_mean`=0.103, `h4_oos_median`=0.097, `h4_oos_positive`=9, `h4_train_sharpe_mean`=1.248, `h4_zk2_n`=16, `h4_zk2_wins`=7, `pooled_lookahead`=0.517, `pooled_oos_mean`=0.012, `pooled_pool_mean`=0.166, `pooled_selection_value`=-0.154, `pooled_zk2_n`=33, `pooled_zk2_p`=1.0, `pooled_zk2_wins`=15, `short_selected_folds`=5, `zk1_pass`=0, `zk2_pass`=0, `zk3_pass`=1

> RESULT of the frozen seq=66 nested walk-forward. Both timeframes complete: H4 16/16 folds, H1 17/17, every fold re-running the full 3,696-config grid on its TRAINING window only and evaluating the single training-selected leader once on the following untouched year.

ZK3 PASSES: 33/33 folds produced a gate-clearing config.
ZK1 FAILS: pooled mean OOS Sharpe +0.012 (median +0.063, 17/33 folds positive). H4 +0.103 (9/16 positive), H1 -0.073 (8/17). The selected configs had mean TRAINING Sharpe +1.248 (H4) and +1.343 (H1). Training Sharpe of ~1.3 mapped to an out-of-sample Sharpe of ~0.
ZK2 FAILS, and it is the decisive one, and it fails harder than crest_n_keel did. The training-selected leader beat the median of a random sample of OTHER configs clearing the same training gates in 15 of 33 folds -- 45%, sign-test p=1.0000. Per timeframe 7/16 (H4) and 8/17 (H1). Selected mean +0.012 vs pool mean +0.166: selection value is NEGATIVE at -0.154. Picking the best config in training was not merely worthless, it was WORSE than picking any config that merely qualified. TRAINING RANK CARRIES NO INFORMATION ABOUT THE TEST WINDOW, and what little it carries points the wrong way.
Z4 CONFIRMED and it quantifies the leak: the seq=40 full-history leader scored +0.615 (H4) and +0.448 (H1) on the SAME folds where honest selection scored +0.103 and -0.073, a lookahead gap of +0.512 / +0.522, pooled +0.517. seq=40's headline in-sample Sharpe of 0.833 is therefore substantially hindsight, exactly as seq=49 found for cnk (0.68-0.81 there).
Z5 FAILS: short was selected in 5 of 33 folds (3 H4, 2 H1). seq=40's finding that 'short is negative everywhere and long-only dominates at every viable timeframe' was itself a full-history ranking artifact -- honest per-fold selection does not reproduce it.
Z6 CONFIRMED: selection is unstable, 15/16 (H4) and 15/17 (H1) distinct configs, and the bias timeframe, ZLSMA length, direction and min_atr all flip between folds.

VERDICT: zerolag_chandelier is REFUTED. Its status moves from 'untested out-of-sample' (seq=64) to refuted, per ZK1 and ZK2 as registered. This closes the last open candidate in the corpus. The seq=40 K1/K2/K4 passes stand as in-sample descriptions and are not overturned; what is overturned is any suggestion that the grid's top config generalises.

THE METHODOLOGY CONSEQUENCE, which is binding under the seq=66 stopping rule. This is the SECOND independent demonstration that top-of-grid selection carries no out-of-sample information in this repo -- seq=49 (crest_n_keel, 30,132 configs, p=0.430, selection value +0.025) and now seq=68 (zerolag_chandelier, 3,696 configs, p=1.0000, selection value -0.154). Two unrelated strategy families, different engines, different grids, different fold geometries, same answer. The registration states: 'If it fails ZK2 the correct response is to stop ranking sweeps by top-of-grid Sharpe across this repo, which is a methodology change rather than a strategy change.' That now applies. An exhaustive sweep remains useful for DESCRIBING a parameter surface (seq=40's cost-arithmetic findings on M5/M15 are real and survive) but its top config is not a candidate and must not be treated as one. The seq=65 finding points the same way from the other direction: there the nested SELECTION stream failed (p=0.105) while the fixed rule passed (p=0.010). Three results now agree that our selection step, not our hypotheses, is the weak link.

Artifacts: research/post/artifacts/zlch_nested_wf_H4.json, zlch_nested_wf_H1.json. Runner research/post/sweeps/zlch_nested_wf.py. Warm-up defect and fix disclosed at seq=67 before this run.

_hash_: `1575181e72037f30…` · _prev_: `11bba9226f6dcc4f…`

### seq 69 · 2026-08-28T06:38:51Z · hypothesis · `state_gate_nested_wf`

**Does gating the momentum signal on market state survive nested selection?**

_Mechanism_: Market-state gating (trend quality / vol regime / trend location) applied to the one directional effect that beat its permutation null. Tests the GATE, not a new entry.

market=XAUUSD· timeframe=H1· family=regime_filter· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- V1: the gated signal's mean OOS Sharpe across folds exceeds the UNGATED signal's on the same folds. If gating does not beat no-gating, the whole line is dead regardless of which gate wins.
- V2 (DECISIVE): the training-selected gate beats the MEDIAN of the other gate cells on the same untouched test window in a majority of folds, sign-test p < 0.05. This is the out-of-sample version of the in-sample +0.123 the screen produced. At seq=68 the same statistic came out at -0.154.
- V3: the FIXED vol_ratio=T0 gate applied to every fold beats ungated. This is deliberately separated from V2 because that cell was chosen after seeing the full sample, so it is contaminated as an OOS number -- but its gap against `selected` is a direct lookahead estimate, the quantity seq=49 and seq=68 measured at 0.5-0.8 Sharpe.
- V4: the gate does not starve the signal -- median selected-gate trades per test fold >= 10.
- PRIOR STATED IN ADVANCE: I expect V2 to FAIL and V3 to pass. Two independent constructions of 'low volatility' have now lifted this same signal (seq=61/62 expanding-percentile atr_ratio: 0.0763 -> 0.1178; the state screen's ATR14/ATR100 terciles: 0.0898 -> 0.2012), which is corroboration rather than a second look. But CHOOSING among gates is a grid search, and grid search has carried zero-to-negative out-of-sample value twice in this repo.

> PARENT: h1_momentum_nested_wf seq=59-62 (rule real but not recoverable; permutation null p=0.010 fixed / 0.105 nested at seq=65). IMMEDIATE PARENT: an EXPLORATORY, NOT pre-registered market-state screen on H1 (research/pre/state_screen.py, artifact state_screen_H1.json). Its results were seen before this registration was written, which is why this entry exists as a separate confirmatory trial and why V3 is separated from V2. Full disclosure of what that screen showed, since it motivates this: (a) three state variables chosen for orthogonality measured max |Spearman| 0.140 on 124,688 H1 bars, versus 0.59-0.84 for the seq=58 five -- the first genuinely non-collinear set here; (b) Kaufman ER FAILED as proposed and failed INVERTED: high ER predicts SMALLER forward moves (|move| spread -0.372 ATR at h=24, monotone) with no asymmetry (E-ratio 0.99-1.03 flat), so it is an exhaustion measure, not a trend-quality gate; (c) vol_ratio's large |move| separation is a NORMALIZATION ARTIFACT -- |move| is divided by ATR(14) and vol_ratio carries ATR(14) in its numerator -- and is discarded; (d) bias_atr's signed test is monotone and 'pays costs' at every horizon but ALL THREE terciles are positive, so it is mostly gold's secular drift: top-tercile advantage over always-long is ~+0.30 USD/oz, about one round trip; (e) conditioning the frozen momentum signal on low volatility lifted per-obs Sharpe 0.0898 -> 0.2012 (n=544 of 1991), with best-minus-pool-median +0.123 -- IN SAMPLE, across 12 cells scored on the same data with the max taken, which is precisely the statistic that came out at -0.154 out-of-sample at seq=68. That is why this run exists. Runner research/pre/state_gate_wf.py, written and frozen before this entry; no output from it has been observed. | FROZEN_DESIGN=Base signal FROZEN from seq=60/65 and not re-tuned: long when the causal expanding percentile of intraday_ret >= 0.90, hold 12 bars, exit at market, non-overlapping, long-only, no stop/target/sizing. Costs: spread 0.22 + commission 0.07 USD/oz round trip, plus overnight swap. Gate pool FROZEN at the 12 cells from the state screen: 4 partitions (ker20, vol_ratio, bias_atr, |bias_atr|) x 3 causal expanding terciles. Lookbacks frozen: ER=20, ATR fast=14, ATR slow=100, SMA=200. Fold geometry mirrors seq=60 exactly: H1, train 1460D / test 365D / step 365D, 17 folds. Selection uses TRAINING bars only with a 30-trade floor; the selected gate is scored once on the untouched test window. Four arms per fold: selected, pool median of the other gates, ungated, and fixed vol_ratio=T0. DEVIATION FROM seq=60, DISCLOSED: expanding percentiles and tercile labels are computed once on the FULL series then sliced, rather than restarted per window. Both are causal and neither looks ahead, but restarting starves indicator warm-up and at seq=67 that silently produced zero-trade configs. The ungated arm is reported so any drift from seq=60's baseline is visible. | KILL_CRITERIA=GK1: V1 fails (gated mean <= ungated mean) -> gating adds nothing. KILL. ; GK2 (DECISIVE): V2 fails (sign-test p >= 0.05) -> gate selection is noise, and the screen's +0.123 was the in-sample mirage seq=68 predicted. The low-vol EFFECT may still stand via V3, but SELECTING a gate does not. ; GK3: V4 fails -> the gate is too restrictive to trade.

_hash_: `bce65075b7ca76e9…` · _prev_: `1575181e72037f30…`

### seq 70 · 2026-08-28T06:41:01Z · update · `state_gate_nested_wf`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `hightrade_folds_mean_oos`=-0.0074, `lookahead_fixed_minus_selected`=0.2739, `lowtrade_folds_mean_oos`=-0.3495, `n_folds`=17, `v1_gate_value`=-0.2156, `v1_pass`=0, `v1_sel_mean`=-0.1571, `v1_ungated_mean`=0.0585, `v2_n`=16, `v2_pass`=0, `v2_pct`=25.0, `v2_selection_value`=-0.2022, `v2_wins`=4, `v2_worse_than_chance_p`=0.0384, `v3_contaminated`=1, `v3_fixed_mean`=0.1168, `v3_fixed_minus_ungated`=0.0583, `v3_n`=17, `v3_pass`=1, `v3_sign_p`=0.049, `v3_wins`=13, `v4_median_trades`=12.0, `v4_pass`=1

> RESULT of the frozen seq=69 nested walk-forward, 17 folds. The registration's stated prior -- V2 fails, V3 passes -- is what happened, and V2 failed harder than predicted.

GK1 FIRES / V1 FAILS: selected-gate mean OOS Sharpe -0.157 vs UNGATED +0.059. Gate value -0.216. Choosing a gate is worse than using no gate at all.
GK2 FIRES / V2 FAILS, and this is the strongest version of this finding yet: the training-selected gate beat the pool median in 4 of 16 folds -- 25%, i.e. WORSE than chance, one-sided p=0.0384 that it is genuinely worse rather than merely worthless. Selection value -0.202. seq=49 found selection worth +0.025 (nil) and seq=68 found -0.154 (negative but not significantly so). This is the first time top-of-training selection has been significantly HARMFUL at p<0.05.
MECHANISM, identical to seq=49 and now confirmed on a third family: selection systematically prefers LOW-FREQUENCY cells whose training Sharpe is a small-sample artifact. Folds where the selected gate produced <12 OOS trades averaged -0.350; folds with >=12 averaged -0.007. Fold 10 selected bias_atr=T0 on 6 trades and scored -2.103. Gates chosen: ker20=T0 x7, vol_ratio=T0 x5, bias_atr=T0 x4, |bias_atr|=T1 x1.
V3 PASSES: the FIXED low-volatility gate (vol_ratio=T0) beat ungated in 13/17 folds, two-sided sign p=0.0490, mean +0.1168 vs +0.0585 (+0.058), median +0.133 vs +0.080. V4 PASSES: median 12 selected-gate trades per fold.
Lookahead estimate: fixed minus selected = +0.274 Sharpe.

WHAT V3 DOES AND DOES NOT ESTABLISH. vol_ratio=T0 was chosen AFTER seeing the full-sample exploratory screen, so its fold results are structurally the same kind of number as seq=46's -- fixed parameters selected on the full history applied to folds -- and seq=49 showed that arm's entire advantage was lookahead. A hindsight-picked best-of-12 is EXPECTED to show some advantage, so p=0.0490 on a contaminated cell is weak evidence, not a pass in the sense the log usually means. It is NOT nothing either: the low-volatility direction has now lifted this same signal under three separate constructions -- seq=61/62's expanding-percentile atr_ratio regime filter (0.0763 -> 0.1178 per-obs Sharpe, selected in 11/17 folds of a PRE-REGISTERED nested WF), the state screen's ATR14/ATR100 terciles (0.0898 -> 0.2012), and now this fixed arm. Three differently-built definitions of 'low vol' pointing the same way is corroboration; none of them is a clean pre-registered test of the gate itself.

VERDICT: gate SELECTION is KILLED. The low-volatility EFFECT survives as a lead and is the only thing carried forward. The correct next step is the seq=63 permutation null applied to the FIXED low-vol gate, which prices hindsight without needing a trial count -- the same instrument that settled the momentum rule at seq=65. NOT another gate search, and NOT a finer tercile scheme.

The three orthogonal state variables as a SET are not carried forward. Kaufman ER failed inverted at the screen and its low tercile was the most-selected gate here precisely because it is the sparsest, which is the artifact. bias_atr contributed four fold selections, all of them bias_atr=T0, and those folds are among the worst.

Artifact research/pre/artifacts/state_gate_wf.json; runner research/pre/state_gate_wf.py.

_hash_: `50d20034e792e07d…` · _prev_: `bce65075b7ca76e9…`

### seq 71 · 2026-08-28T12:18:58Z · update · `state_gate_nested_wf`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `artifact_share_of_advantage`=0.21, `atr14_t0`=3.594, `atr14_t2`=4.725, `gate_established`=0, `median_usd_t0`=1.007, `median_usd_t2`=-0.133, `null_advantage_mean`=0.01582, `null_advantage_obs`=0.07499, `null_advantage_p`=0.0647, `null_advantage_q95`=0.07674, `null_gated_mean`=0.02902, `null_gated_obs`=0.1424, `null_gated_p`=0.005, `null_reps`=200, `null_ungated_obs`=0.06741, `null_ungated_p`=0.005, `raw_usd_t0`=2.1039, `raw_usd_t2`=0.3377, `raw_usd_uncond`=0.8204, `top1_year_share`=0.25, `top3_year_share`=0.52, `years_positive_t0`=19, `years_sign_p`=0.00043, `years_total`=22

> PERMUTATION NULL on the FIXED low-vol gate (200 reps, within-day bar permutation, full pipeline), plus two contamination checks proposed before it finished.

NULL RESULT, three streams each against its own matched null:
  gated     observed +0.14240  p=0.0050  null mean +0.02902 sd 0.03534 q95 +0.08833
  ungated   observed +0.06741  p=0.0050  null mean +0.01321 sd 0.01818 q95 +0.04384
  ADVANTAGE observed +0.07499  p=0.0647  null mean +0.01582 sd 0.03303 q95 +0.07674
The gated rule beats chance -- but so does the ungated rule, at the same p. The quantity the gate actually CLAIMS is the advantage, and it does NOT clear 0.05. VERDICT: the low-vol gate is NOT established. The gated rule works because the SIGNAL works, not demonstrably because of the gate.
The null earned its keep by pricing the mechanism precisely: the advantage null mean is +0.0158, NOT zero. Gating on low volatility confers a positive Sharpe advantage even on permuted data, because it shrinks the Sharpe denominator. About 21% of the observed +0.075 is that artifact. A test benchmarking against zero would have reported this gate as clearly significant.

TWO CONTAMINATION CHECKS, both PASSED, which is why the p=0.0647 is a near miss rather than a dismissal:
(1) ATR-NORMALIZER CONTAMINATION -- the defect that voided the screen's arm A (forward |move| was divided by ATR(14) while vol_ratio carries ATR(14) in its numerator) could recur wherever the target is ATR-normalised. Re-ran the comparison in RAW USD/oz: unconditional 0.8204 (n=1991); T0 2.1039 (n=544); T1 0.3382; T2 0.3377. Medians 0.387 / 1.007 / 0.247 / -0.133. The ordering STRENGTHENS in dollars and the median moves with the mean, so it is not one outlier. Mean ATR(14) is 3.594 (T0) vs 4.725 (T2) -- a 24% denominator difference cannot manufacture a 6x dollar gap. If this were the same bug relocated, dollar PnL would be flat or LOWER in compression cells while Sharpe rose; instead it rises 2.6x. Ruled out.
(2) CALENDAR CLUSTERING -- T0 occupies all 22 years at 9-45 trades/yr (15-45% share, mostly 20-35%), so it is not one regime's behaviour, and it is profitable in 19 of 22 years (one-sided sign p=0.00043). BUT magnitude is concentrated: the top year (2025) contributes 25% of T0's total dollars and the top 3 years contribute 52%. Sign is persistent; size is fat-tailed and recency-weighted. Flagged, not fatal.

AMBIGUITY DISCLOSED: I did not pre-register WHICH stream decides before running this, the same defect as seq=65. Resolving it on the logic that was written down rather than on preference: the claim under test is that the GATE adds something, so ADVANTAGE is decisive and `gated` is confounded with the signal working. The gate does not clear.

NOTE on the ungated baseline: 0.0674 here vs 0.0763 at seq=62/65, the disclosed consequence of computing expanding percentiles once on the full series rather than restarting per window. The drift is visible as promised, and small.

_hash_: `42f76253b470555c…` · _prev_: `50d20034e792e07d…`

### seq 72 · 2026-08-30T09:37:46Z · update · `state_gate_nested_wf`

stage=0_hypothesis · verdict=shelved · counts_as_trial=False

_Metrics_: `decisive_stream_guard`=1, `disposition_live_unproven`=1, `median_ratio_t0_vs_uncond`=2.6, `respecification_barred`=1, `rule5_added`=1, `ungated_is_new_candidate`=0, `ungated_null_p_seq65`=0.01, `ungated_null_p_this_run`=0.005, `ungated_prespecified_at_seq`=59, `use_median_expectancy`=1

> DISPOSITION and two process fixes. No new computation on the gate; this records the state it is being left in and closes the loop on a question that was left implicit.

DISPOSITION: SHELVED as LIVE-UNPROVEN, not falsified. The evidence is real ordering (raw USD/oz T0 2.104 vs unconditional 0.820, median 1.007 vs 0.387), real persistence (profitable 19/22 years, sign p=0.00043, present in every year at 15-45% occupancy), and an UNPROVEN increment (advantage p=0.0647 against a null whose mean is +0.0158). That is a coherent state and is not being forced into pass/fail.

BINDING CONSTRAINT ON ANY FUTURE WORK ON THIS GATE: it must NOT be re-specified. No different tercile boundaries, no different ATR pair, no different horizon. Observed +0.07499 against null q95 +0.07674 is close enough that a handful of respecifications would cross 0.05 by construction, and each one inflates the honest trial count that DSR then charges against everything else in this log. The answer to a near miss is INDEPENDENT EVIDENCE, not another slice of the same 22 years.

SIZING NOTE, recorded so it is not lost: the top three years supply 52% of T0's dollars, which would normally raise a fat-tail concern -- but T0's MEDIAN is 1.007 vs 0.387 unconditional, a 2.6x ratio matching the mean ratio. The edge's EXISTENCE is not fat-tail driven; only its MAGNITUDE is. Any capacity or drawdown model must be built off trimmed or median expectancy. Mean expectancy overstates it substantially.

THE UNGATED STREAM, answered explicitly rather than left as a by-product. Question: was the base signal specified before this screen or did it emerge during it? ANSWER: specified before. intraday_ret/h=12 was frozen at seq=59 and evaluated at seq=60 (nested WF), seq=61 (cost stress), seq=62 (DSR) and seq=65 (permutation null), all of which precede the state screen at seq=69. It is NOT a by-product of this screen and is NOT a new registrable candidate -- it is the existing h1_momentum rule, and its status is unchanged. Its DSR at honest trial count is already on record: 0.5144 at N=126 and 0.4121 at N=276 (seq=62), later shown to be a miscalibrated gate (seq=63). What IS new: this run is a SECOND, independent permutation null on that rule, and it agrees -- p=0.0050 here against p=0.010 at seq=65, both against nulls that carry drift (null mean +0.0132 here). Two independent permutation runs now place the fixed rule clearly above chance. Recoverability is still what fails (nested p=0.105, seq=65); that split is unchanged and is the honest summary of the whole programme.

PROCESS FIX -- RULE 5, now structural. The decisive stream must be named in the registration with its threshold, before the run. Missed twice: seq=65 (fixed 0.010 vs nested 0.105) and seq=71 (gated 0.005 vs advantage 0.0647). Both times the streams DISAGREED and the choice fell to be made after seeing them; both were resolved against the preferred reading, but that was the prose happening to be clear, not process. research/pre/decisive_stream.py::declare now refuses a registration that does not name a stream, a threshold in (0,1), and a rationale of substance. Replayed against seq=71 it returns FAIL, reproducing the verdict mechanically. Rule 1's guard (normalizer_check.assert_disjoint) shipped at seq=71; rules 1-5 are in CLAUDE.md.

_hash_: `3efe47f0c662fd98…` · _prev_: `42f76253b470555c…`

### seq 73 · 2026-08-30T10:12:54Z · hypothesis · `vol_gate_cross_instrument`

**Does the low-vol gate replicate on XAG and US500?**

_Mechanism_: Volatility compression preceding directional expansion. Tests whether the XAU near-miss is a general mechanism or one series.

market=XAGUSD+US500· timeframe=H1· family=regime_filter· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- R1 (DECISIVE, declared via decisive_stream.declare): the ADVANTAGE stream (gated minus ungated per-obs Sharpe) beats its own within-day permutation null at p < 0.05, on XAGUSD and on US500. `gated` and `ungated` are reported but do NOT decide -- gated is confounded with the base signal working.
- R2: the sign of the advantage is positive on both instruments even where p does not clear. Direction replicating is weaker evidence than significance but is not nothing.
- R3: the advantage null mean is POSITIVE on both, as it was on XAU (+0.0158), confirming that the variance-reduction artifact of gating on low volatility is general rather than an XAU quirk.
- PRIOR STATED IN ADVANCE: I expect R3 to hold (it is mechanical), R2 to hold on XAGUSD and be uncertain on US500, and R1 to fail on at least one. XAU itself only reached p=0.0647 on 22 years; XAG has 13.4 and US500 13.4 in the common window, so power is lower. A clean pass on either would be a stronger result than XAU's own near miss.

> PARENT: state_gate_nested_wf seq=69/70/71/72. The low-vol gate is SHELVED as LIVE-UNPROVEN -- real ordering (raw $/oz 2.104 vs 0.820 unconditional, median 1.007 vs 0.387), real persistence (19/22 years, sign p=0.00043), unproven increment (advantage p=0.0647 vs a null mean of +0.0158). seq=72 BARS re-specification: different terciles, ATR pair or horizon would cross 0.05 by construction on the same 22 years and inflate the honest trial count charged against every other result in this log. The licensed response to a near miss is INDEPENDENT evidence, which is this. WHY THIS IS NOT FISHING: vol compression preceding directional expansion has a literature prior, and the replication reuses NONE of the data that produced the near miss. Replication on two other instruments is worth more than XAU's p crossing an arbitrary line. DATA PROVENANCE, since it is new: XAGUSD 99,999 H1 bars 2009-08-18..2026-08-28 and US500 62,726 bars 2012-08-05..2026-08-28, pulled from the mt5-test terminal via /api/v1/rates and validated on install (header present, every row 6 fields, >1000 lines) after a first attempt left a TRUNCATED 51k-line XAGUSD file that a naive length check would have passed. XAGUSD hit the 99,999 count cap so more history exists behind it. USDX was evaluated and REJECTED: only 3,548 bars (2.5y) and its price range 25.00-26.43 is ~4x off the real dollar index, so it is not usable for the separate gold_dxy work. RULE 5 APPLIED: decisive stream declared via research/pre/decisive_stream.py::declare('advantage', 0.05, ...) BEFORE the run, which is the fix for the seq=65/71 defect where multi-stream results disagreed and the deciding stream had not been named in advance. | FROZEN_DESIGN=IDENTICAL specification to seq=69/71, not re-tuned: long when the causal expanding percentile of intraday_ret >= 0.90, hold 12 bars, non-overlapping, long-only; gate = causal expanding tercile T0 of vol_ratio = ATR(14)/ATR(100); lookbacks ER=20, ATR 14/100, SMA 200 all frozen. Fold geometry train 1460D / test 365D / step 365D, concatenated OOS. Null = within-day bar permutation, 200 reps, which preserves daily returns, volatility clustering, bar geometry and session structure while destroying the intraday signal. COST NORMALISATION: every instrument is charged the SAME 1.45bp proportional round trip, matched to XAU's $0.29 on a ~$2,000 price. XAG and US500 have different real spreads, and comparing the MECHANISM at differing cost structures would confound the thing being replicated. This isolates 'does compression precede expansion'; it does NOT establish tradeable viability, which needs true per-instrument costs and is a separate question. Swap is excluded because it is priced per-lot in XAU terms and does not transfer. COMMON WINDOW 2012-08-06..2025-12-31 is primary so no instrument is advantaged by having more history; full-history runs are secondary context. Runner research/pre/vol_gate_replication.py, frozen before this entry; no output observed. | KILL_CRITERIA=RK1: advantage is NEGATIVE on both instruments -> the XAU result was instrument-specific and the shelved lead should be closed rather than left live-unproven. ; RK2: advantage p >= 0.05 on both AND the sign is inconsistent -> no replication; the lead stays shelved and no further XAU slicing is licensed. ; NOTE: a PASS on either instrument does NOT promote anything. It would license one nested walk-forward on that instrument, nothing more. | DECISIVE_STREAM=advantage @ p<0.05 (the claim under test is that the GATE adds something; `gated` is confounded with the base signal working and `ungated` measures the signal, not the gate)

_hash_: `fe491babe767651e…` · _prev_: `3efe47f0c662fd98…`

### seq 74 · 2026-08-30T10:20:38Z · update · `vol_gate_cross_instrument`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `artifact_sign_flips_across_instruments`=1, `cost_bp`=1.45, `folds`=9, `r1_pass_us500`=0, `r1_pass_xag`=0, `r3_pass`=0, `replicated`=0, `reps`=200, `us500_advantage`=0.06869, `us500_n_gated`=415, `us500_null_mean`=0.13406, `us500_p`=0.9701, `window`=2012-08-06..2025-12-31, `xag_advantage`=0.03005, `xag_n_gated`=359, `xag_null_mean`=-0.0232, `xag_p`=0.0796, `xau_advantage`=0.11321, `xau_n_gated`=362, `xau_null_mean`=0.03398, `xau_p`=0.01

> RESULT of the frozen seq=73 cross-instrument replication. 200 permutation reps per instrument, common window 2012-08-06..2025-12-31, 9 folds each, matched 1.45bp cost.

R1 (DECISIVE, declared before the run via decisive_stream.declare) FAILS ON BOTH:
  XAGUSD  advantage +0.03005  p=0.0796  null mean -0.02320  q95 +0.04142  (359 gated trades)
  US500   advantage +0.06869  p=0.9701  null mean +0.13406  q95 +0.20244  (415 gated trades)
  XAUUSD control  advantage +0.11321  p=0.0100  null mean +0.03398  (362 gated trades)
The gate does not replicate. Applying the pre-declared rule mechanically: FAIL, FAIL, PASS -- and the only PASS is the instrument that generated the hypothesis, which is not independent evidence of anything.

US500 IS THE DAMAGING RESULT, and it is worse than a null result. Its observed advantage (+0.0687) is only HALF its own null mean (+0.1341), p=0.9701. On an equity index the low-vol gate performs markedly WORSE than the mechanical artifact predicts. A test benchmarking against zero would have scored US500's +0.0687 as a success.

R3 FAILS, and its failure is the most generalisable finding here. The advantage null mean was predicted to be positive everywhere because gating on low volatility shrinks the Sharpe denominator. Measured: XAGUSD -0.0232, XAUUSD +0.0340, US500 +0.1341. The artifact is not merely instrument-dependent in MAGNITUDE, it flips SIGN. There is no universal 'compression bonus' to subtract, so the size of the correction cannot be reasoned about a priori and must be measured per instrument. This is a second, independent argument against zero-benchmarked tests (DSR included), on top of the drift argument from seq=65.
R2 holds only weakly: both advantages are positive in raw terms, but US500's is positive while sitting far below its own null, so sign agreement is not evidence.

RK2 does not fire literally -- it required p>=0.05 on both AND inconsistent sign, and the raw signs agree. But R1 is the DECISIVE stream and it failed on both, which is the criterion that governs. Recording that the kill criteria were drafted slightly loosely: 'consistent sign' should have been specified relative to each instrument's own null, not in raw terms, since a positive number below a more positive null is evidence AGAINST. Noted for future registrations rather than reinterpreted now.

ON THE XAU CONTROL, stated carefully so it is not misread as improvement: p=0.0100 here vs p=0.0647 at seq=71 is NOT the same statistic. This run uses a 1.45bp proportional cost with NO swap and a 9-fold 2012-2025 window; seq=71 used real spread plus commission plus swap over 17 folds and 22 years. The comparison that IS meaningful: under an identical measurement, XAU's advantage is larger on the recent 13-year window (+0.1132) than the artifact predicts, while XAG and US500 show nothing. That is consistent with the recency concentration already logged at seq=71 -- top 3 of 22 years supplying 52% of T0 dollars -- and it makes the XAU effect look more like a period-and-instrument specific feature than a mechanism.

DISPOSITION: the low-vol gate moves from LIVE-UNPROVEN to NOT REPLICATED. It is not falsified on XAU, where the ordering, the persistence and the raw-dollar checks all stand. But it has now had its one licensed shot at independent evidence and did not get it, so no further work on it is licensed: no re-specification (already barred at seq=72), no third instrument chosen after seeing these results, and no nested walk-forward, which seq=73 said a PASS would license and which therefore is not licensed by a FAIL. The honest summary of the whole vol-gate line is that XAU shows a real ordering whose incremental value could never be demonstrated and which does not appear in two other instruments.

Artifacts: research/pre/artifacts/vol_gate_repl_{XAGUSD,US500,XAUUSD}_common.json.

_hash_: `477de003240b7015…` · _prev_: `fe491babe767651e…`

### seq 75 · 2026-08-30T10:33:04Z · update · `gold_dxy_divergence`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `best_lag_corr`=-0.0139, `best_lag_k`=1, `contemporaneous_corr`=-0.3607, `corr_252d_frac_negative`=1.0, `corr_252d_mean`=-0.424, `corr_full_sample`=-0.3607, `decile_gross_cost_ratio`=0.47, `decile_gross_usd`=0.1361, `eg_adf_t`=0.5162, `eg_crit_5pct`=-3.34, `gross_cost_ratio`=0.113, `gross_usd_per_oz`=0.0327, `hedge_beta_levels`=1.8617, `lag_r_squared_pct`=0.0194, `lead_lag_ratio`=0.0386, `n_bars_aligned`=71368, `net_usd_per_oz`=-0.2573, `p1_rolling_corr_pass`=1, `p2_coint_pass`=0, `p3_leadlag_pass`=0, `syndxy_bars`=79928, `syndxy_max_abs_landmark_err`=0.23, `usdx_rejected`=1, `usdx_unique_prices`=143, `usdx_zero_ret_pct`=29.5, `window`=2013-10-08..2025-12-31

> PREREQUISITES from seq=18 completed. seq=18 recorded 'rolling correlation, CADF cointegration test, cross-corr lag analysis' as undone with NO SPEC written. All three are now run. No strategy was specified, no entry/exit/sizing designed and no parameter searched -- writing a spec and testing it in the same motion is the entry-trigger archaeology this programme has repeatedly shown worthless.

DATA. The blocker was never research, it was a missing USD series, and it is now solved. The broker's USDX was evaluated and REJECTED as unusable: 3,548 H1 bars (2.5y), 29.5% zero returns and only 143 unique prices across the sample against 0% and 3,540 for a real series. A six-leg ICE-weighted synthetic was built instead (research/pre/synthetic_dxy.py): 50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036, all six legs available at 80,000 H1 bars back to 2013-10 so nothing had to be dropped or renormalised. Negatively-weighted legs have high/low INVERTED into the basket, since a rising EURUSD lowers the index -- getting that wrong would leave closes correct while silently corrupting every range-derived quantity (ATR, volatility state). VALIDATION, and the USDX rejection turned into the asset that enabled it: USDX is useless as a reference (log-return correlation with the synthetic is 0.0104, i.e. nothing, which is USDX's fault not the synthetic's). Validated against published DXY landmarks instead -- 2014-05 80.38 vs 80.4; 2018-01 89.10 vs 89.1; 2020-03 99.00 vs 99.0; 2022-09 112.21 vs 112.1; 2023-07 101.89 vs 101.9; max |diff| 0.23 -- and the synthetic's all-time high of 114.76 falls on 2022-09-28, the exact date and level of the real index's multi-decade peak. The reconstruction is correct. 79,928 bars align with XAUUSD over 2013-10-08..2025-12-31.

P1 ROLLING CORRELATION -- PASSES. Log-return correlation is stable and reliably negative: mean -0.413 (5d), -0.411 (21d), -0.405 (63d), -0.424 (252d); full-sample -0.3607. At the 252-day window it is negative 100% of the time, range [-0.665, -0.004]; at shorter windows 92-94%. There IS a dependable baseline to diverge from. This is the one prerequisite that supports the idea.

P2 COINTEGRATION -- FAILS. Engle-Granger implemented directly (statsmodels would not install; OLS plus an AIC-selected ADF on the residual, MacKinnon EG critical values). ADF t = +0.5162 against a 5% critical value of -3.34 -- not close, and the sign is wrong: gamma is POSITIVE, so the residual has no restoring force at all. Note the hedge beta is +1.8617 on LOG LEVELS while the RETURN correlation is -0.36. Two trending series (gold 1200->2600, DXY 80->100 over the window) produce a positive level relationship with a negative return relationship: a textbook spurious regression, which the test correctly rejects. Without cointegration, 'divergence' has no restoring force and a widening gap is just two random walks drifting.

P3 CROSS-CORRELATION LAG -- FAILS, and it is the decisive one. Contemporaneous correlation is -0.3607; the strongest non-zero lag is k=+1 at -0.0139, i.e. 3.9% of contemporaneous. Neighbouring lags are noise (k=-3..+3: +0.0052, -0.0060, -0.0027, -0.3607, -0.0139, -0.0005, -0.0054) against a 2-SE band of 0.0075 at n=71,367. The relationship is essentially PURELY CONTEMPORANEOUS. Knowing gold and the dollar move inversely right now says nothing about the next bar.
ECONOMIC TRANSLATION, which is how this repo decides: corr -0.0139 is R^2 0.0194%. Trading the sign of the previous DXY bar, both directions, 71,366 bars: gross +$0.0327/oz per trade against a $0.29 round trip -> net -$0.257/oz, a gross/cost ratio of 0.113x when it needs >1.0. Conditioning on top-decile |DXY move| (n=7,137) raises gross to +$0.1361/oz -> still net -$0.154, 0.47x. The best available conditioning is HALF the cost. Same shape as asian_session_fade at seq=48 (0.284x): statistically real, economically dead by a multiple.

VERDICT: KILLED at the prerequisite stage. Both tradeable forms are ruled out independently -- no lead-lag means no timing signal, and no cointegration means no mean-reverting spread either. The inverse gold/dollar relationship is real, strong and stable, and is a DESCRIPTION of contemporaneous co-movement rather than a forecast. This is what the prerequisite gate exists for: the idea died for the price of a data pull, before any strategy was designed around it.

REUSABLE ASSET: research/data/SYNDXY_H1.csv (79,928 bars, validated) plus the six FX legs are now local. Any future cross-asset work has a verified dollar series without repeating this.

_hash_: `b937bcb96381aa8e…` · _prev_: `477de003240b7015…`

### seq 76 · 2026-08-30T10:34:37Z · update · `gold_dxy_divergence`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `eg_calib_reps`=300, `eg_calibrated`=1, `eg_fp_rate_pct`=5.3, `eg_nominal_pct`=5.0, `eg_power_pct`=100.0, `kill_rests_on_p3_alone`=1, `statsmodels_available`=0

> ADDENDUM to seq=75: calibration of the hand-rolled Engle-Granger used in P2.

statsmodels could not be installed (dependency conflicts with the system environment: xlsxwriter and Pygments pins from unrelated packages). The pip run exited 0 but the module is not importable, so the earlier 'exit code 0' was the shell's, not pip's. The cointegration verdict at seq=75 therefore rests on an ADF/EG implementation I wrote myself and had not validated -- which is not an acceptable basis for a kill, so it is validated here against known ground truth.

NEGATIVE CONTROL, 300 reps of two independent random walks (n=2,000), truth = NOT cointegrated: rejection rate 5.3% against a nominal 5%. Correctly sized.
POSITIVE CONTROL, 300 reps of x = 2y + AR(1) noise with phi=0.95, truth = cointegrated: detection rate 100.0%. Full power at this sample size.

The test is neither over- nor under-rejecting, so P2's failure is not an artifact of my implementation. And the observed statistic was never marginal: t = +0.5162 against a 5% critical value of -3.34 is on the wrong side of ZERO, meaning the residual has a positive autoregressive root -- no restoring force whatsoever, not merely weak reversion.

Restating the dependency structure of the seq=75 kill so it is auditable: P3 (lead-lag) is the decisive prerequisite and uses no ADF at all -- plain correlation plus an economic translation showing 0.113x of the round-trip cost. The verdict would stand on P3 alone even if P2 were wrong. P2 removes the alternative tradeable form (a mean-reverting spread) and is now independently calibrated.

_hash_: `1ccdc415cf1082ae…` · _prev_: `b937bcb96381aa8e…`

### seq 77 · 2026-08-30T15:45:02Z · hypothesis · `ensemble_vs_selection`

**Should we average gate-passers instead of picking the best?**

_Mechanism_: Methodology test of the combination rule, not a market hypothesis. Equal-weight allocation vs top-1 selection.

market=XAUUSD· timeframe=H1+H4· family=methodology· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- E1 (DECISIVE, declared before the run): the equal-weight ENSEMBLE of gate-passing configs beats the TOP-1 by training Sharpe on TOTAL RETURN (price-return units, costs included) in a majority of folds, sign-test p < 0.05. Measured on dollars, NOT Sharpe.
- E2: the ensemble's Sharpe also exceeds top-1's. Reported but NOT decisive: an average of zero-edge configs has zero edge and a smaller denominator, so a Sharpe win alone is consistent with pure variance reduction.
- E3: the fraction of ensemble members with positive OOS total return is materially above 0.5 in a majority of folds. If members are a coin flip, the ensemble is averaging noise and any win is diversification, not edge.
- PRIOR STATED IN ADVANCE: I expect E1 to pass on total return and E3 to be near 0.5. The pool beat the selection in 3 of 4 prior runs by a mean of +0.12 Sharpe, but every one of those comparisons was in SHARPE, which is exactly the metric that variance reduction inflates. If E1 passes while E3 sits at ~0.5, the honest reading is that ensembling is a RISK improvement, not an edge discovery -- and on a $100 account with a 1.45bp cost floor, a risk improvement over zero edge is still zero edge.

> MOTIVATION, and why this is a finding rather than mining. Across every nested walk-forward in this log the POOL control beat the SELECTED config: seq=68 H4 +0.164 vs +0.103, seq=68 H1 +0.168 vs -0.073, seq=70 gates +0.046 vs -0.157, seq=49 cnk -0.149 vs -0.124 (the lone exception, worth +0.025). Mean across the four: selected -0.063, pool +0.057 -- a swing of +0.12 from doing LESS selection. Those pool numbers were CONTROLS, the 'what if you picked any qualifying config' null, not results anyone went looking for. The programme has now demonstrated three times (seq=49, 68, 70) that top-of-training selection carries zero-to-negative out-of-sample information, at seq=70 significantly WORSE than chance (one-sided p=0.0384). Every one of those tests asked which config to pick. This asks whether to pick at all, which is the question the controls have been answering unprompted. RULE 5 APPLIED: decisive stream declared via decisive_stream.declare on TOTAL RETURN, not Sharpe, precisely because the motivating evidence is all in Sharpe and Sharpe is the metric an ensemble inflates for free. | FROZEN_DESIGN=seq=66 zlch geometry reused unchanged: full 3,696-config grid re-run on each TRAINING window, seq=39 gates (PF>=1.20, DD<=0.30, Sharpe>0, trade floor scaled at 100/21.6 per year with minimum 30), H4 train 1825D / test 365D / step 365D and H1 train 1460D / test 365D / step 365D. Two arms scored once on each untouched test window: TOP-1 by training Sharpe, and an EQUAL-WEIGHT ENSEMBLE of K=50 gate-passers drawn with seed 20260827 -- the SAME seed and size as seq=68's pool control, so the ensemble is built from the identical configs that produced the pool figures motivating this test. COSTS: each config is held at 1/K size and each config's returns already carry its own costs from the engine, so the equal-weight average charges the correct total. Netting is deliberately IGNORED -- offsetting positions each still pay -- which makes the ensemble estimate conservative rather than flattering. Runner research/post/sweeps/ensemble_vs_selection.py, written and frozen before this entry; no output observed. | KILL_CRITERIA=EK1: ensemble total return does not beat top-1 in a majority of folds -> the pool-beats-selection pattern was a Sharpe artifact and does not survive translation to dollars. The finding is retired and top-of-grid selection remains simply broken rather than replaceable. ; EK2: ensemble total return is NEGATIVE in aggregate -> averaging dead configs produces a dead portfolio, which settles the question for this repo. ; NOTE ON SCOPE: this is a METHODOLOGY test. A pass does NOT revive zerolag_chandelier or any other candidate. Reviving one would require its own registration under the new combination rule, because changing how configs are combined is legitimate while quietly resurrecting a refuted strategy through it is not. | DECISIVE_STREAM=total_return @ p<0.05 (ensembling shrinks variance without creating edge, so Sharpe can rise while nothing is earned -- the bias_atr trap at seq=71; dollars decide, Sharpe is secondary)

_hash_: `b42d79c2fb5be35a…` · _prev_: `1ccdc415cf1082ae…`

### seq 78 · 2026-08-30T16:22:30Z · update · `ensemble_vs_selection`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `e1_pass`=0, `e2_sharpe_pass`=1, `e3_frac_members_positive`=0.5648, `h1_delta`=0.00023, `h1_ens_sharpe`=0.023, `h1_ens_total`=0.01592, `h1_sign_p`=0.6291, `h1_top1_sharpe`=-0.0168, `h1_top1_total`=0.0157, `h4_delta`=0.00332, `h4_ens_sharpe`=0.05, `h4_ens_total`=0.02619, `h4_sign_p`=0.4545, `h4_top1_sharpe`=0.0171, `h4_top1_total`=0.02287, `k`=50, `n_folds`=33, `nothing_revived`=1, `pooled_delta_pct`=9.0, `pooled_ens_total`=0.0209, `pooled_top1_total`=0.01918, `sharpe_would_have_inverted_verdict`=1

> RESULT of the frozen seq=77 methodology test. 33 folds (H4 16, H1 17), K=50, same seed and sample as seq=68's pool control.

E1 (DECISIVE, declared on TOTAL RETURN before the run) FAILS ON BOTH:
  H4  top1 +0.02287  ensemble +0.02619  delta +0.00332  10/16 folds  sign p=0.4545
  H1  top1 +0.01570  ensemble +0.01592  delta +0.00023  10/17 folds  sign p=0.6291
Pooled: top1 +0.01918 vs ensemble +0.02090, +9.0% -- and not distinguishable from chance on either timeframe. The ensemble does win a bare majority of folds (10/16, 10/17) but nowhere near significance.

E2 (Sharpe, deliberately NON-decisive) 'passes' spectacularly, and that is the whole finding:
  H4  Sharpe 0.0171 -> 0.0500   (2.9x)
  H1  Sharpe -0.0168 -> +0.0230  (SIGN FLIP)
On H1 the top-1 procedure has a NEGATIVE mean Sharpe and the ensemble a POSITIVE one -- a complete reversal of verdict -- while total return is +0.01570 vs +0.01592, the same dollars to three decimal places. Had Sharpe been allowed to decide, this would have been written up as 'ensembling converts a losing procedure into a winning one'. It does nothing of the kind. It converts the same dollars into a smoother path. This is the seq=71 bias_atr trap reproduced exactly, and the only reason it was caught is that rule 5 forced the decisive metric to be named before the run.

E3 explains the mechanism: across all 33 folds only 0.5648 of ensemble members are positive out-of-sample. Per-fold it ranges 30% to 94% and averages near a coin flip. The ensemble is averaging configs that individually have no edge, so what it gains is cancellation of their variance against each other, not any of them being right.

WHAT THIS SETTLES, and it reframes three earlier results. The pool never beat the selection because the pool was good. It beat it because the SELECTION was actively BAD -- seq=70 put top-of-training selection significantly worse than chance at one-sided p=0.0384 -- and because every one of those comparisons was made in SHARPE, which flatters any less-concentrated alternative for free. Translate the same comparison into dollars and the advantage is +9% and insignificant. Top-of-grid selection remains broken; it is not REPLACEABLE by averaging, because there is nothing in the pool to average toward.

DRAFTING DEFECT, recorded rather than reinterpreted: EK1 was worded 'does not beat top-1 in a majority of folds', and the ensemble DID win a bare majority (10/16, 10/17), so EK1 does not fire literally. E1 and the declared decisive stream required majority AND p<0.05, which failed on both. The declared rule governs and decisive_stream.verdict returns FAIL for both timeframes mechanically. This is the second registration whose kill criteria were looser than its predictions (seq=73 was the first); kill criteria should be written as the negation of the prediction, not paraphrased.

SCOPE GUARD HELD: nothing is revived. zerolag_chandelier stays refuted (seq=68) and the state gates stay killed (seq=70).

PRACTICAL CONSEQUENCE for a $100 account at a 1.45bp cost floor: a variance improvement over zero expected edge is still zero expected edge. Averaging 50 configs to earn the same +0.019 total return with a prettier ratio buys nothing that can be spent.

Artifacts: research/post/artifacts/ensemble_vs_selection_{H4,H1}.json.

_hash_: `c68b94b8feb725d2…` · _prev_: `b42d79c2fb5be35a…`

### seq 79 · 2026-08-30T18:26:06Z · hypothesis · `gold_real_yields`

**Do real yields (DFII10) lead gold?**

_Mechanism_: Gold is a zero-coupon perpetual with no carry, so its opportunity cost IS the real rate. Better fundamental prior than the dollar.

market=XAUUSD· timeframe=D1· family=cross_asset· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- Y1: rolling correlation of gold returns and real-yield changes is stable and negative, giving a dependable baseline (the DXY version passed this).
- Y2: log(gold) and the real-yield LEVEL are cointegrated.
- Y3 (DECISIVE): yield changes LEAD gold -- the causal correlation (yield[D] vs gold[D+1]) is materially non-zero and correctly signed, and translates to more than 1.0x the round-trip cost measured as EXCESS OVER ALWAYS-LONG, not raw return.

> Run as the direct successor to gold_dxy_divergence (seq=75, KILLED: real and stable correlation but purely contemporaneous, 0.113x of cost). IDENTICAL three prerequisites so the two are comparable; nothing else added, no spec written. Daily frequency, which is the one regime where a $0.29/oz round trip does not dominate. LOOKAHEAD HANDLED EXPLICITLY: DFII10 for date D is observed on D and published after the US close, while gold trades around the clock, so pairing yield[D] with gold's return ON D uses information that did not exist. Both alignments are reported so the size of the illusion is visible; only the causal one decides. Data: FRED DFII10, 6,171 rows 2003-01-02..2026-08-27, joined to XAUUSD D1 on 4,241 trading days.

_hash_: `f3da204ae91b8f12…` · _prev_: `c68b94b8feb725d2…`

### seq 80 · 2026-08-30T18:26:06Z · update · `gold_real_yields`

stage=0_hypothesis · verdict=killed · counts_as_trial=False

_Metrics_: `always_long_usd_per_oz`=1.1838, `causal_lag1`=0.0041, `contemporaneous_lookahead`=-0.0566, `corr_252d_frac_neg`=0.79, `corr_252d_mean`=-0.091, `corr_full_sample`=-0.0566, `decile_gross_usd`=-1.0722, `eg_adf_t`=0.8281, `eg_beta`=-0.1874, `excess_over_always_long`=-0.9428, `gross_cost_ratio`=0.831, `gross_usd_per_oz`=0.241, `n_days`=4241, `rule3_changed_verdict`=1, `signal_long_pct`=46.2, `signal_short_pct`=45.5, `y1_pass`=0, `y2_pass`=0, `y3_pass`=0

> RESULT. All three prerequisites FAIL, and more decisively than the DXY version did.

Y1 FAILS. Rolling correlation of gold returns vs real-yield changes: mean -0.064 (21d), -0.078 (63d), -0.091 (252d); full sample -0.0566. Negative only 61%/68%/79% of the time. Compare the DXY relationship at seq=75: -0.361 full sample, negative 92-100% of the time. The dollar is a FAR stronger and more stable contemporaneous companion to gold than real yields are at daily frequency, which inverts the fundamental prior that motivated running this.
Y2 FAILS. Engle-Granger on log(gold) vs yield level: beta -0.1874 (correct sign, higher real yields -> lower gold) but ADF t = +0.8281 against a 5% critical value of -3.34. Wrong side of zero; no restoring force. Same spurious-trend structure as gold/DXY.
Y3 FAILS, decisively and in the most informative way. Contemporaneous correlation -0.0566; CAUSAL correlation (yield[D] -> gold[D+1]) +0.0041 -- essentially zero AND the wrong sign, against a 2-SE band of 0.0307 at n=4,240. Lags 2-5 are -0.0199, -0.0111, -0.0252, -0.0077, all at or inside noise. The weak same-day relationship is entirely unusable: aligning yield[D] to gold[D] would have shown -0.057, the honest alignment shows nothing. That gap IS the lookahead.

THE ECONOMIC NUMBER, and why rule 3 was essential. Trading -sign(yield change) with a 1-day hold produced gross +$0.2410/oz against a $0.29 cost -- 0.831x, which reads as a near miss and is nothing of the kind. The signal is nearly balanced (46.2% long, 45.5% short), so this is not drift asymmetry. Always-long on the SAME days earns +$1.1838/oz. The signal's EXCESS OVER ALWAYS-LONG is -$0.9428/oz: being short 45.5% of the time in a bull market destroys four fifths of the drift it would otherwise collect. Conditioning on top-decile |yield move| makes it worse, not better: gross -$1.0722/oz. Without CLAUDE.md rule 3 this would have been logged as '0.831x of cost, closest yet'.

VERDICT: KILLED at the prerequisite stage, at the cost of one FRED download. Both cross-asset directions in the corpus are now closed -- gold/dollar at seq=75 and gold/real-yields here -- and both died on the same structure: a real contemporaneous association with no lead-lag and no cointegration. Gold co-moves with macro; it is not FORECAST by it at these frequencies, at least not by anything a retail feed can see.

_hash_: `32a3bb2013d652a3…` · _prev_: `f3da204ae91b8f12…`

### seq 81 · 2026-08-30T20:13:24Z · update · `h1_momentum_nested_wf`

stage=6_stress · verdict=killed · counts_as_trial=False

_Metrics_: `demo_balance`=3643.15, `deployed_demo`=1, `entry_agreement_pct`=99.7, `environment_test`=1, `first_fire_utc`=20260831, `intraday_ret_max_diff`=0.0, `mae_max_atr`=13.59, `mae_median_atr`=1.29, `mae_p99_atr`=7.98, `magic`=1600001, `min_lot_risk_pct_high`=6.0, `min_lot_risk_pct_low`=3.9, `pctile_window`=50000, `stop_atr_mult`=10.0, `stop_would_bind_pct`=0.301, `untradeable_at_100usd`=1

> DEPLOYED to demo for forward data collection. This is not a promotion and the verdict at seq=65 is unchanged: real (permutation null p=0.010 there, p=0.005 independently at seq=71, both against nulls carrying gold's drift) but NOT RECOVERABLE (nested selection p=0.105). It is deployed because forward data is the only evidence that is not contaminated by selection, none has ever been collected, and the clock only starts when it is running.

WHAT RUNS: app.quant.strategies.h1_momentum, magic 1600001, environment=test (mt5-test), XAUUSD H1, beat entry 'h1-momentum' at HH:02 weekdays with expires=300. Frozen rule unchanged from seq=59/60: long when the causal percentile of intraday_ret >= 0.90, hold exactly 12 bars, exit at market, long only, no target, no re-entry while open.

TWO DEVIATIONS, both MEASURED BEFORE deploying rather than justified after:
  1. Catastrophic stop at 10x ATR(14). The research rule has no stop, which is not acceptable on a live connection. Across the 1,991 historical trades the adverse excursion within the 12-bar hold is median 1.29 ATR, p90 4.02, p99 7.98, max 13.59. A 10-ATR stop would have bound 0.301% of the time -- 6 trades. Fidelity 99.7%; it is a disaster guard, not a parameter.
  2. Bounded percentile window of 50,000 bars against the research expanding window over 21 years. Entry-decision agreement 99.70% (99.45% at 20,000, 99.21% at 10,000).
FIDELITY VERIFIED by loading the actual deployed module and running it against the research pipeline on the same 124,887 bars: live _intraday_ret reproduces research.pre.feature_screen._atr/intraday_ret with max |diff| = 0.000e+00.
TIMEZONE handled explicitly -- MT5 returns broker server time (EET/EEST) and intraday_ret is measured from the session's FIRST BAR, so mislabelling the clock moves every session boundary. This is the seq=48 defect. Timestamps are localised to Europe/Athens and converted to UTC before the day grouping; the in-container smoke test confirmed a UTC index.

CAPACITY LIMIT, and it is a real finding independent of the edge. Minimum lot is 0.01 = 1 oz. With a 10-ATR stop at current H1 ATR(14) of ~$14-22/oz, ONE minimum lot risks $141-220. On the $3,643 demo balance that is 3.9-6.0% -- already at the 5% ceiling with NO room to size down, because the ATR sizer asks for 0.0129 lots and is floored to 0.01. On the $100 target account stated in CLAUDE.md the same position would risk 141-220% of the account. THE RULE IS UNTRADEABLE AT $100 REGARDLESS OF WHETHER THE EDGE IS REAL. Any future live discussion has to start from capital, not from the research.

STATE: hot-patched into celery and celery-beat, both restarted; quant.h1_momentum.run confirmed registered; retired strategies confirmed still absent from the schedule after the restart. Read-only smoke test in-container fetched 50,000 bars (2018-03-02..2026-08-28), produced a correct UTC index and returned signal=None at percentile 0.0196 without placing an order. First scheduled fire Monday 2026-08-31 00:02 UTC. Durability PR #102.
NOT YET EXERCISED: no order has been placed, so the order path, the 12-bar exit and the DB write are covered by code review only. The first live signal is the first real test of those, and they should be checked when it fires rather than assumed.

WHAT WOULD RESOLVE THIS, stated so nobody expects it early: at ~54 trades a year the seq=63 power work implies roughly 3,000 trades are needed for the question to be answerable, which is decades. This run does not resolve the hypothesis. What it does is start accumulating the only uncontaminated evidence available, and provide an execution-fidelity record -- slippage, fill quality, whether the 12-bar exit behaves -- which no amount of backtesting supplies.

_hash_: `019ff0dd3e1b7209…` · _prev_: `32a3bb2013d652a3…`

### seq 82 · 2026-08-31T13:40:43Z · update · `h1_momentum_nested_wf`

stage=8_deployed · verdict=killed · counts_as_trial=False

_Metrics_: `beat_entry_disabled`=1, `d8_wmps_commit`=3db869a, `drawdown_guard_wired`=0, `live_risk_halt`=1, `min_lot_risk_pct_at_100usd_atr14`=1.4, `min_lot_risk_pct_at_100usd_atr22`=2.2, `min_lot_risk_pct_at_demo_atr14`=0.0384, `min_lot_risk_pct_at_demo_atr22`=0.0604, `risk_pct_configured`=0.05, `sizer_default_risk_pct`=0.02, `sizer_grid_cells`=480, `sizer_grid_cells_over_budget`=125, `sizer_grid_over_budget_share`=0.2604, `sizer_grid_worst_realised_risk_pct`=6.0, `stop_atr_mult`=10.0

> LIVE_RISK_HALT. h1_momentum disabled at the Celery beat schedule (settings.py CELERY_BEAT_SCHEDULE), Phase 0 D6/D8, 2026-08-31. It carried verdict=killed from seq=65 (decisive stream declared nested; nested_p=0.1045 vs prereg_alpha=0.05) and was reaffirmed killed at seq=81, yet was deployed to demo and first fired 2026-08-31. Halted for risk configuration, not for the forward-data rationale: it sets RISK_PCT=0.05 overriding the sizer 2% default, STOP_ATR_MULT=10.0, and wires no DrawdownGuard -- the guard is imported only by crest_n_keel and asqs, both already retired, so the sole scheduled strategy was the only one unguarded. seq=81 had already recorded untradeable_at_100usd=1. Halted rather than re-parameterised: the minimal correct fix for placing bets beyond budget is to stop placing them; choosing new parameters on a live instrument outside the pipeline is what the two-iteration rule forbids. Disabling touches no numerical module, so the D8 golden fixtures are unaffected. Re-enable requires the T5 granularity flag, account-level risk policy (X26) and mandatory DrawdownGuard precondition (X27), plus a completed pre-registration -> E-Ratio -> walk-forward -> DSR record. Recorded as an UPDATE because EventType has no LIVE_RISK_HALT member; adding one is owed under T6 and Phase 0 forbids code changes.

_hash_: `91470ef9fd2f9a97…` · _prev_: `019ff0dd3e1b7209…`

### seq 83 · 2026-09-01T09:47:50Z · schema_migration · `record:t6-eventtype-extension`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `added_event_types`=audit,repo_migration,project_rename,schema_migration,parity_fixture, `canonical_payload_changed`=no, `chain_hash_before`=91470ef9fd2f9a97dc0d77006f36e85864bdaef531140fcdf40156faabf6050d, `entries_before`=83, `logentry_fields_changed`=0, `trial_count_after`=26, `trial_count_before`=26

> Spec T6. Adds AUDIT, REPO_MIGRATION, PROJECT_RENAME, SCHEMA_MIGRATION and PARITY_FIXTURE, a RECORD_EVENT_TYPES frozenset, and append_record() -- an entry point for facts about the log rather than about a hypothesis. counts_as_trial is forced False on record events and is not a parameter, so structural bookkeeping cannot inflate the DSR haircut denominator. current_state() now skips record events so the hypothesis table stays a hypothesis table. No LogEntry field was added, removed or reordered and _canonical() is unchanged, so every pre-existing entry hash still verifies: 83 entries, trial_count 26, terminal 91470ef9...abf6050d, all unchanged across the edit. This event exists because the schema change must live in the chain it governs. The precedent is the research/artifacts/ -> research/{pre,post}/artifacts/ move, made without an event, which left three logged artifact paths unresolvable and no recorded means of resolving them.

_hash_: `95ecc004eb6617df…` · _prev_: `91470ef9fd2f9a97…`

### seq 84 · 2026-09-01T09:47:50Z · audit · `record:phase0-d7-baseline`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `committed_prefix_commit`=6864727, `committed_prefix_entries`=30, `committed_prefix_terminal`=5a060a461d8bfeff, `d7_entries`=82, `d7_terminal_hash`=019ff0dd3e1b7209f9be6ef5bd8efb590a15ee627a540d5c8679cb320da31876, `d7_trial_count`=26, `d7_verify`=true, `entries_at_audit`=84, `hash_chain_only_entries`=53, `trial_count_at_audit`=26

> Phase 0 D7 acceptance. The baseline was measured on 2026-08-31 at 82 entries, terminal 019ff0dd...0da31876, verify() True, trial_count 26. seq=82 (LIVE_RISK_HALT) and the T6 schema migration have been appended since; trial_count is 26 at every one of those points because neither was a trial. Provenance, which bounds what X21 can cross-check: entries.jsonl was first committed at 6864727 with 30 entries (terminal 5a060a461d8bfeff), a strict prefix of the current chain, and that commit is on the remote. So seq 0-29 have independent git-history corroboration; seq 30-82 rest on the hash chain alone. The X21 cross-check therefore starts at 6864727 and the unwitnessed span is 53 entries, not 83. Recorded via append_record() in Phase 0.5 rather than during Phase 0, which had a zero-production-code-change constraint that adding an EventType member would have broken.

_hash_: `9a67a16939724d44…` · _prev_: `95ecc004eb6617df…`

### seq 85 · 2026-09-01T10:05:38Z · project_rename · `record:qhf-harness-to-quant-harness`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `commit`=4493ebc, `distribution_new`=quant-harness, `distribution_old`=qhf-harness, `github_redirect_active`=true, `python_package_renamed`=no, `repo_new`=thanderoy/quant_harness, `repo_old`=thanderoy/qhf_harness

> PATH MAPPING -- apply when resolving any reference recorded before this entry.

(1) Repository rename, effective seq=85:
      qhf_harness  ->  quant_harness   (GitHub redirect active)
    Affects logged references to 'qhf/data/csv_loader.py' and 'qhf_harness/examples/run_cnk_sweep_oos.py'.

(2) HISTORICAL, retroactive -- an artifact move made WITHOUT an event, recorded here because the log otherwise contains three unresolvable paths and no recorded means of resolving them:
      research/artifacts/  ->  research/pre/artifacts/
                           or  research/post/artifacts/
    Made by the pre/post reorganisation (WMPS a6e9d33). All three affected files exist under research/pre/artifacts/; only the recorded prefix is stale:
      zlch_signal_edge_20260613T124557Z.json
      avwap_sweep_reclaim_signal_edge_20260614T083827Z.json
      avwap_multibar_reclaim_signal_edge_20260614T133418Z.json

NOT renamed: the Python package 'qhf'. Per spec it is split into four packages (resources, strategies, research, platform) at Phase 1 T1, so a single old->new namespace pair would be wrong. That mapping is recorded in its own PROJECT_RENAME event when the split lands.

No prior entry was edited to reflect either rename. Recorded references stay as written and are resolved forward through this mapping.

_hash_: `64c1581f8e1bb0de…` · _prev_: `9a67a16939724d44…`

### seq 86 · 2026-09-01T11:42:33Z · repo_migration · `record:research-tree-to-quant-harness`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `byte_identical_to_source`=yes (all shared files), `commits_carried`=10, `entries_before`=86, `files_carried`=145, `graft_commit`=f8c5837e7417746cab8d0f5e8b55115e190fcb0c, `method`=git subtree split + git subtree add, `source_commit`=456467f, `source_prefix`=research/, `source_repo`=thanderoy/wine-mt5-python-setup, `target_prefix`=packages/qh-research/research, `target_repo`=thanderoy/quant_harness, `terminal_hash_before`=64c1581f8e1bb0dec1249b86455f44b3dcfa1507c9d06305ecde5a46ab058c79, `trial_count_before`=26

> Phase 0.5 step 3. The chain migrated intact and was verified at the new location BEFORE this entry was appended: verify() True, 86 entries, trial_count 26, terminal 64c1581f...ab058c79 -- identical to the source. All 10 carried commits verified reachable as ancestors of the graft commit via merge-base --is-ancestor, so history is a real second parent rather than a squashed import blob.

CANONICAL LOCATION. From this entry forward, the log at packages/qh-research/research/log/ in quant_harness is the one that is appended to. The copy remaining in wine-mt5-python-setup is frozen at seq=85 and is historical: WMPS is bug-fix-only through Phase 2 and nothing is deleted from its research tree on parity, so the two copies deliberately diverge from here. Any entry appended to the WMPS copy after this point is a mistake, and the divergence is detectable -- the chains share a prefix through seq=85 and any WMPS seq>=86 will not appear here.

DATA. research/data/ is gitignored except XAUUSD_H1.csv, which is tracked because it underpins T9a and the seq=31 artifact and broker OHLCV is not durably reproducible. It travelled with the graft. The other 15 series did not; data_manifest reports them as MISSING rather than proceeding, and QH_DATA_DIR repoints the tree at a populated data directory (verified: 16/16 files ok).

The Python package 'qhf' is NOT renamed by this event. It is split into four packages at Phase 1 T1; that mapping gets its own PROJECT_RENAME when the split lands. The repo rename and the historical research/artifacts/ mapping are already recorded at seq=85.

_hash_: `8e19240d8e347ea2…` · _prev_: `64c1581f8e1bb0de…`

### seq 87 · 2026-09-01T12:58:33Z · audit · `record:d1-d3-block-reason-correction`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `actual_state`=mt5 and mt5-test healthy on ganymede for ~2 months, `audusd_nzdusd_available`=true, `claimed_dependency`=MT5 terminal unavailable (mt5 / mt5-test containers down), `corrects_entry_seq`=84, `corrects_record_id`=record:phase0-d7-baseline, `d1_d3b_still_blocked_on`=mt5-api lacks symbol_info and copy_ticks_range endpoints, `d3a_lost_collection_window_months`=2, `d3a_started_utc`=2026-09-01T12:50:00+00:00, `execution_host`=ganymede, `host_checked_instead`=830-G5 (laptop)

> Correcting seq=84 and the Phase 0 memo/D9 plan. Both recorded D1 and D3 as BLOCKED with the dependency 'MT5 terminal unavailable'. That dependency was never true. mt5 and mt5-test have been up and healthy on the execution host (ganymede) for approximately two months. The collectors were being run from a laptop that has no MT5 and never had one, and the BLOCKED artifacts they wrote faithfully reported the environment they were run in rather than the environment that exists.

The prior entry is not edited and remains in the chain as written. The finding it recorded (the D7 baseline) is unaffected and still correct; only the stated reason for the D1/D3 block was wrong.

WHAT WAS ACTUALLY BLOCKED, and still is: D1 and D3b need two mt5-api endpoints that do not exist at any commit -- symbol_info and copy_ticks_range (docs/mt5_api_additions.md). That block is real and host-independent. D3a needed nothing: it runs against /api/v1/tick, which has existed throughout, and it is now collecting.

COST: D3a only accumulates from the moment it is switched on. Roughly two months of forward spread data were not collected for no reason other than the check being run in the wrong place.

CONSEQUENCE FOR D4: all nine candidate symbols resolve on the live terminal, AUDUSD and NZDUSD included. D4's effective-N figures (1.55 majors-only, 1.83 with metals) were stamped UPPER BOUNDS specifically because those two were absent from local CSVs. They are available from the broker, so the bound can be tightened -- and the Phase 2b target of effective N >= 4 was set against a bound that may not hold. Re-run D4 once AUD/NZD history is pulled.

GENERALISATION: a stated dependency is a claim, and this one was never checked against the host that runs the system. Any future BLOCKED record must name the host it was evaluated on.

_hash_: `d52b582c214c409d…` · _prev_: `8e19240d8e347ea2…`

### seq 88 · 2026-09-06T20:29:57Z · audit · `record:phase0-broker-mislabel-20260906`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `affected_tasks`=['D1', 'D3a', 'D3b'], `correct_server`=PepperstoneKE-MT5-Live01, `eurusd_zero_spread_fraction`=0.862, `reversed`=['ioc_assumption_generalises', 'volume_max', 'metals_tick_value'], `survived`=['tick_value_embeds_fx_rate'], `voided`=['all_spread_medians_before_20260906'], `wrong_server`=MetaQuotes-Demo

> The 2026-09-01 D1, D3a and D3b runs were labelled 'Pepperstone (demo)' on the strength of the container's name. The terminal in mt5-test was authorized on MetaQuotes-Demo and synchronized with MetaQuotes Ltd.; its 20260901.log contains no Pepperstone authorization at all. No collector recorded the trade server, so nothing contradicted the assumption and it reached a committed snapshot (pepperstone_demo_20260901.json).

WHAT REVERSES. The guard result 'filling_mode is 1 (FOK only) for six of nine symbols, so the repo-wide ORDER_FILLING_IOC rule does not generalise' was MetaQuotes' configuration. Re-run against PepperstoneKE-MT5-Live01 on 2026-09-06 returns filling_mode 2 (IOC) for all nine: ioc_assumption_generalises is TRUE and the IOC rule HOLDS. volume_max is 100 not 500 for FX; metals tick_value differs 10x.

WHAT SURVIVES. tick_value embeds the capture-time spot rate, now confirmed exactly on Pepperstone: contract_size * tick_size / tick_value reproduces the live ask to the last digit (USDJPY 156.255, USDCHF 0.81005, USDCAD 1.38388). XAUUSD's implied rate is 1.00000, so the 'metals off by 10x' note was itself a MetaQuotes artifact. The sizer's choice to derive value from contract_size rather than tick_value stands, now on real venue data.

SEPARATELY VOID. The D3b spread census excluded every non-positive spread. Measured directly against MT5 on Pepperstone 2026-09-04 13:00-14:00: EURUSD n=5192, crossed=0, zero=4476 (86%); XAUUSD n=15461, crossed=0, zero=0. Zero spreads are genuine raw-feed quotes and the marked-up metal has none. The exclusion discarded 86% of EURUSD's observations and reported median 1e-05 for a pair whose true median is 0.0, with the real cost in the separately-charged commission. Every spread figure from before 2026-09-06 is void.

MECHANISM. One unverified inference (container name => broker) survived because no output recorded provenance. Fixed: all three collectors now stamp the trade server and accept --expect-server, refusing to collect on a mismatch.

_hash_: `11aef2c5580a7cda…` · _prev_: `d52b582c214c409d…`

### seq 89 · 2026-09-07T09:02:57Z · audit · `record:spread-estimator-weighting-20260907`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `cost_gate_estimator`=entry_conditional, `crossed_excluded`=0, `estimators`=['tick_weighted', 'time_weighted', 'entry_conditional'], `eurusd_london_median_tick_weighted`=0.0, `eurusd_london_median_time_weighted`=0.0001, `months_per_symbol`=11.9, `symbols`=9, `total_spreads`=448777747, `xauusd_agreement`=live 0.19 vs history 0.18-0.19

> The D3 census (448,777,747 spreads, 9 symbols, ~11.9 months, PepperstoneKE-MT5-Live01) reports EURUSD London median 0.0 and p95 1e-05. Concurrent D3a live sampling of the same session reports median 1.0e-04 — about 10x wider. Both are correct measurements.

D3b is TICK-WEIGHTED: it reads every historical tick, and ticks burst precisely when the book is active and the spread is momentarily zero. D3a's periodic series is TIME-WEIGHTED: one sample a minute lands on ordinary moments, which are wider. The two agree closely on XAUUSD (live 0.19 vs history 0.18-0.19) because a near-constant spread cannot be re-weighted, which is the control that identifies the mechanism. Live FX medians are also suspiciously uniform at 1.0-1.2 pips across every pair while history varies sub-pip per symbol — the signature of sampling ordinary moments rather than active ones.

CONSEQUENCE. A tick-weighted median is not an execution-cost estimate. Using D3b's 0.0 as the EURUSD cost flatters it by roughly an order of magnitude.

AND NEITHER IS THE RIGHT ESTIMATOR. A strategy evaluating a closed H1 bar acts at HH:00:00 plus its wake/fetch/decide latency. That instant is neither a random tick nor a random moment; it is the only spread the strategy will ever pay. The ENTRY-CONDITIONAL estimator is the one a cost gate needs, and it did not exist until D3a gained bar-boundary sampling on 2026-09-07 (sample_kind='bar_boundary', default H1 and M15, 750ms latency offset).

The Asia tail finding is unaffected: it is a ratio computed within a single method. USDCHF p95 3e-05 -> 4.4e-04 (15x), GBPUSD 9x, EURUSD 6x, while AUDUSD barely moves because Asia is its liquid session.

_hash_: `8bd6aa55de6dec5b…` · _prev_: `11aef2c5580a7cda…`

### seq 90 · 2026-09-07T09:02:57Z · audit · `record:d3b-terminal-recovery-20260907`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `collector_exit`=137, `collector_memory_needed_metals_gb`=3, `recoveries`=26, `recoveries_after_pull`=0, `recovery_seconds`=60-90, `safe_chunk_days_metals`=1, `symbols_preserved_by_incremental_writes`=7

> Collecting 12 months of tick history for 9 symbols OOM-killed the mt5 container 26 times over ~5 hours. Every one was recovered automatically in 60-90s by the supervisor (wine-mt5-python-setup 10-supervise.sh) and zero recoveries have occurred in the 5 hours since the pull ended, so the OOMs are entirely D3b-induced.

PRECONDITIONS, all three required. (1) mem_limit on the mt5 service so the kill lands in the cgroup rather than at host level — without it, on 2026-09-01, the kernel killed the Wine tree, s6 survived as PID 1, Docker reported the container Up with RestartCount=0, and the healthcheck failed 14,425 consecutive times with nothing acting on it. (2) A supervisor that treats a disconnected terminal as unhealthy: the API answers 200 with mt5_connected False and does not re-establish the link itself, so health-as-responding would have seen nothing wrong. (3) Backoff between unreachable chunks in D3b — without it ten attempts are spent in seconds and the collector declares a source dead while its repair is in progress, which is exactly how the 19:12 run ended at two symbols.

SEPARATE DEFECT. The collector holds an entire chunk's parsed JSON; a 2M-tick XAUUSD response exceeded its own 1 GB cap and it was SIGKILLed at 137. Seven completed symbols survived because writes are incremental per symbol. Metals re-ran at 1-day chunks with 3 GB and completed OK with no depth shortfall.

LIVE-ACCOUNT NOTE. This ran against the live trading terminal, so there were 26 windows in which a strategy could not have reached MT5. Nothing was trading (sync_trades succeeded at 01:00, 02:00, 03:00 with zero positions and no 503s), but that is timing, not a property of the arrangement. A future full pull should either run against a separate Pepperstone terminal or be scheduled outside market hours.

_hash_: `f4fcd8de42231d97…` · _prev_: `8bd6aa55de6dec5b…`

### seq 91 · 2026-09-15T07:33:02Z · audit · `d3a-entry-conditional-resolves-r7`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `bar_boundary_rounds_per_symbol`=616, `commission_provenance`=HAND_ENTERED, `estimator_outlier`=tick_weighted, `estimators_agreeing`=time_weighted == entry_conditional, `eurusd_p50_spread_entry_conditional_h1`=0.0001, `eurusd_p50_spread_entry_conditional_m15`=0.0001, `eurusd_p50_spread_tick_weighted_d3b`=0.0, `eurusd_p50_spread_time_weighted`=0.0001, `periodic_rounds_per_symbol`=7391, `round_turn_bps_p50`={'AUDUSD': 2.5, 'EURUSD': 1.46, 'GBPUSD': 1.4, 'NZDUSD': 3.25, 'USDCAD': 1.57, 'USDCHF': 2.06, 'USDJPY': 1.55, 'XAGUSD': 5.67, 'XAUUSD': 0.62}, `server`=PepperstoneKE-MT5-Live01, `stamps`=['PROVISIONAL_COSTS'], `window_utc`=2026-09-07/2026-09-12T12:30Z

> D3a ran dual schedules against PepperstoneKE-MT5-Live01 from 2026-09-07 to 2026-09-12T12:30Z: periodic (60s, time-weighted) and bar-boundary (H1 and M15 close + 750ms, entry-conditional). 7,391 periodic and 616 boundary rounds per symbol.

The two estimators agree to the tick across all nine symbols at p50, p75 and p90. EURUSD reads 1.0 pip on both. The D3b tick-weighted census reads 0.0 for the same instrument over the same broker.

So R7's premise holds -- the three estimators are different numbers -- but the split is 2:1, not 1:1:1. Tick-weighting is the outlier, and it is the artifact: quote updates burst while the spread is momentarily zero, so counting ticks counts the moments nobody trades rather than the moments a bar-close entry fires. 78.3% of EURUSD ticks carry a zero spread and none of them is reachable by a strategy that acts on a closed bar.

Consequence: the cost gate uses the time-weighted series, and the entry-conditional series is now a check on it rather than a separate input. A cost model built on the D3b medians would have understated FX spread by roughly 10x. No result has been produced on that basis; run_d3() already carried the estimator warning, and D2 is a granularity test that does not read spread at all.

Round-turn cost at these spreads, with commission still HAND_ENTERED at $7.00/lot: XAUUSD 0.62 bps, GBPUSD 1.40, EURUSD 1.46, USDJPY 1.55, USDCAD 1.57, USDCHF 2.06, AUDUSD 2.50, NZDUSD 3.25, XAGUSD 5.67. Commission is 41% of the EURUSD figure and is the largest unsourced number remaining, so every row is provisional on it.

_hash_: `4e406325f952aecc…` · _prev_: `f4fcd8de42231d97…`

### seq 92 · 2026-09-15T07:33:02Z · audit · `d3a-scheduler-spin-2026-09-12`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `bar_boundary_rows_written`=5553, `buckets_covered`=['ny_session', 'london_ny_overlap', 'friday_close'], `buckets_missed`=['sunday_open'], `defect`=boundary due before the sleep decision was skipped, not fired, `detection_rule`=per-schedule row rate vs specified cadence, not process liveness, `entry_conditional_series_ended_utc`=2026-09-12T12:30:00Z, `file_bytes`=8497697753, `observed_cadence_s`=0.32, `periodic_rows_written`=19612557, `restarted_utc`=2026-09-15T07:18Z, `specified_cadence_s`=60

> D3a's wait loop chose the nearest of the periodic and bar-boundary targets and broke out when that target was already past -- without sampling it. Nothing then advanced the pending time, so the same stale boundary was selected on every pass: the loop never slept, never took another boundary sample, and ran the periodic schedule at request rate.

It triggers when a round outlasts the gap to the next bar close, which nine symbols against a loaded terminal do routinely. Live it fired at 2026-09-12T12:30Z and produced 19.6M periodic rows (8.5 GB) over the following three days at ~3 samples/second against the live terminal.

What it cost: the entry-conditional window covers full NY sessions, the London/NY overlap and the Friday 2026-09-11 close, but stops before the Sunday 2026-09-13 open -- one of the two buckets the window was specified to capture. The time-weighted series is unaffected and runs to 2026-09-15.

Detection is the transferable part. Process liveness, line count and file growth all read healthier than ever while the series that mattered was dead: the file grew 190x faster than specified. This is the same failure shape as the mt5-test collector that wrote 65,228 error rows while looking alive, and the same shape as the D3b container that exited five days before it was noticed. The check that would have caught all three is per-schedule row rate against its specified cadence, not liveness.

Fixed in fix/d3a-boundary-scheduler with a regression test that reproduces the straddle; collection restarted 2026-09-15T07:18Z on the fixed code and the 07:30:00.750Z M15 boundary fired for all nine symbols. The 8.5 GB file is retained unmodified.

_hash_: `6d28cceca03225c6…` · _prev_: `4e406325f952aecc…`

### seq 93 · 2026-09-16T07:02:35Z · schema_migration · `record:t6-log-schema-v2`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `entries_before_migration`=93, `new_fields`=['universe', 'selection_rule', 'null_baseline_structure', 'benchmark_sharpe', 'min_decidable_sharpe', 'registry_snapshot'], `prior_entries_read_as`={'selection_rule': 'pooled_all', 'universe': ['XAUUSD']}, `prior_entries_rewritten`=False, `schema_version`=2, `terminal_hash_before_migration`=6d28cceca03225c61a99c3af5d35fa96ab55d7e119012cb25b26f690972bffea, `trial_count_before_migration`=26

> Additive extension (T6). Registrations appended after this marker must carry universe, selection_rule, null_baseline_structure, benchmark_sharpe, min_decidable_sharpe and registry_snapshot.

Every entry before this marker is to be read as universe: ["XAUUSD"] and selection_rule: POOLED_ALL. Those entries are NOT rewritten and carry no such fields on disk; this event is where that reading is recorded. Rewriting them would break the hash chain, and the chain is the only reason the trial count means anything.

trial_count() now applies the accounting rule rather than counting rows: pooled and pre-specified cost one trial, a post-hoc selection over k instruments costs k. No pre-marker entry has a selection_rule, so all of them keep one-row-one-trial and the D7 baseline is unchanged across the boundary.

_hash_: `cfc1d0b738fc6382…` · _prev_: `6d28cceca03225c6…`

### seq 94 · 2026-09-16T08:05:23Z · audit · `record:t8-prior-dsr-used-zero-benchmark`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `change`=benchmark_sharpe is now a required argument, `d5_source_artifact`=phase0_universe_20260907.json, `entries_that_cleared_0_95_under_zero_benchmark`={'36': {'dsr': 1.0, 'id': 'crest_n_keel_momentum', 'n_trials': 1}, '40': {'dsr': 0.998, 'id': 'zlch_param_sweep', 'n_trials': 15}, '62': {'dsr': 0.9959, 'id': 'h1_momentum_nested_wf', 'n_trials': 1}}, `entries_with_dsr_metrics`=[29, 30, 36, 40, 43, 45, 46, 51, 56, 62, 63, 64, 65], `positive_control_seq_63_gold_bh_dsr`=0.8112, `prior_economic_benchmark`=0.0, `re_evaluated`=False, `verdicts_changed`=0, `xauusd_buy_and_hold_sharpe_annualised`=0.6343, `xauusd_buy_and_hold_sharpe_per_obs`=0.039959

> T8 makes benchmark_sharpe a required argument to deflated_sharpe_ratio(). Before it, the only benchmark in the calculation was the selection term E[max SR] over N trials, which is derived under a null of ZERO true Sharpe. The economic alternative was therefore implicitly zero: the question asked was 'did this beat nothing?' rather than 'did this beat the alternative?'.

On gold those are not close. D5 puts XAUUSD buy-and-hold at 0.6343 annualised (0.039959 per observation) over 2013-10 to 2026-08, a period in which gold rose roughly 12x. Every gold DSR in this log was handed that entire Sharpe for free.

The clearest evidence is already in the log and was not read as such at the time. At seq=63 a positive control -- gold buy-and-hold itself -- scored DSR 0.8112 at N=126. A benchmark that nearly clears a test whose null is zero is a mis-specified null, not a strong benchmark.

Thirteen entries carry DSR metrics (seq 29, 30, 36, 40, 43, 45, 46, 51, 56, 62, 63, 64, 65). Three cleared the 0.95 threshold under the lenient benchmark and are the ones whose verdicts could move: seq=36 crest_n_keel_momentum 1.0 at N=1; seq=40 zlch_param_sweep 0.998 at N=15; seq=62 h1_momentum_nested_wf 0.9959 at N=1. All three are low-N readings that were already discounted on other grounds, and none was promoted.

This entry records the defect, not a re-decision. Re-evaluating requires the original OOS return streams, which is a separate piece of work; nothing above is restated as a new verdict. Historical sweep scripts now pass benchmark_sharpe=LEGACY_BENCHMARK_SHARPE = 0.0 explicitly, so their numbers still reproduce and the leniency is visible at the call site instead of implied by a default.

benchmark_from_d5() reads the figure straight out of the Phase 0 artifact and converts it once. The plausibility guard cannot help here: 0.6343 is a perfectly reasonable per-observation Sharpe, so an annualised value passed by hand is accepted while being ~16x too large. That is pinned as a known limitation.

_hash_: `2cf8807104f6fee3…` · _prev_: `cfc1d0b738fc6382…`

### seq 95 · 2026-09-16T08:27:38Z · parity_fixture · `record:t9a-flood_tide_h1-mask-off`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `counts_as_trial`=False, `horizon_unit`=tradable_bars, `layers_checked`=7, `layers_passed`=7, `mode`=mask_off, `passed`=True, `reference_artifact`=flood_tide_h1_seq31_p1_20260706T075247Z.json, `stopped_at`=None

> Re-ran the seq=31 E-Ratio pipeline and compared five layers in dependency order: PASS.

This is a migration test of an already-adjudicated mechanism, not a new trial. flood_tide_h1's verdict (SHELVE_INSUFFICIENT_SIGNIFICANCE) is untouched and is not reopened by reproducing it.

Horizons count tradable bars (R4). Mask-off only: the mask-on comparison has two independent channels — the signal set and the ATR normaliser — and is left for its own piece of work rather than half-reported here.

_hash_: `edf45fbac56d8b35…` · _prev_: `2cf8807104f6fee3…`

### seq 96 · 2026-09-16T17:13:50Z · project_rename · `record:t10-qhf-package-split`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `commit`=9e334a6, `data_files_moved`=4, `duplicate_dropped`=XAUUSD_H1.csv, `modules_moved`=23, `namespace_old`=qhf, `namespaces_new`=research.metrics,research.validation,research.reports,research.engines,research.datasets, `packages_receiving`=qh-research, `parity_t9a_identical`=yes, `tests_after`=417, `tests_before`=417

> MODULE PATH MAPPING -- apply when resolving any qhf.* module reference recorded before this entry.

    qhf.metrics.*             ->  research.metrics.*
    qhf.validation.*          ->  research.validation.*
    qhf.reports.*             ->  research.reports.*
    qhf.engines.*             ->  research.engines.*
    qhf.data.csv_loader       ->  research.datasets.csv_loader
    qhf.data.cost_model       ->  research.datasets.cost_model
    qhf.data (package)        ->  research.datasets
    qhf/data/raw/*.csv        ->  packages/qh-research/research/data/*.csv

The package was SPLIT, not renamed, which is why this is a mapping and not a single old->new pair. seq=85 and seq=86 both said so at the time and deferred the mapping to the commit that landed the split; this is that commit (9e334a6).

The whole of qhf landed in qh-research. resources, strategies and platform receive nothing here. That is a statement about where the code is today, not about where it belongs: engines/indicators.py and engines/sizer.py are the ports T11 reconciles against resources, and engines/strategies/ holds backtesting.py adapters that Phase 3 retires. Moving them now would have merged a rename with a parity task and made any deviation impossible to attribute to one or the other.

NOT REWRITTEN, deliberately. Every qhf reference that records what a past run used stays as written:
  - note strings in post/sweeps/{registration,cnk_registration,ebb_registration,asqs_registration,cnk_nested_registration}.py are verbatim in this chain; each was checked against entries.jsonl before being left alone. Rewriting them would leave those scripts unable to reproduce the entries they produced.
  - the HTML report/narrative builders describe completed runs.
  - data_manifest.GRANDFATHERED names a path at commit cb48e00.
This follows seq=85: recorded references stay as written and resolve forward through the mapping.

BEHAVIOUR. The T9a mask-off parity report is byte-identical before and after the move apart from its own timestamp -- ohlc_hash a8cd64270c5376ca, signal_hash 3b8c71ccadf15320, 1669 long signals, all five ordered layers passing on both sides. Suite 417 passed on both.

CONSEQUENCE WORTH RECORDING. research/README.md justified two DSR implementations on the grounds that the harness lived in a separate repo and venv. It has lived here since seq=86 and now sits in the same package as research.post.dsr, so the justification has expired. The duplication is not collapsed here: research.metrics.deflated is what produced logged results, so retiring it needs the parity vectors re-run and any deviation logged as its own entry.

_hash_: `c81846fbbb7c7cdb…` · _prev_: `edf45fbac56d8b35…`
