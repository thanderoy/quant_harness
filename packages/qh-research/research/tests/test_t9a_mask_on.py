"""T9a mask-on — the decomposition holds together and nothing is unexplained.

Acceptance criterion 3 asks for the mask-on divergence to be *attributed*, not
merely measured, so these tests are mostly about the attribution being real:
that the two channels are separable, that the arithmetic closes, and that the
unattributed bucket is empty for a reason rather than because nothing was
checked.

No ``pytest.mark.x`` here on purpose. Criterion 3 is not an X id — X15a and
X15b are the mask-*off* checks — and inventing a marker would make the
coverage gate in ``tests/test_x_coverage.py`` report a frontier that moved
when it did not.

The full run needs the seq=31 OHLC, which lives in the WMPS repo, so the heavy
tests skip on a runner exactly as T9a's do. What does not need the data — the
decomposition algebra and the mask construction — is tested unconditionally.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from resources.data.mask import MaskReason
from research.parity import t9a_mask_on as m
from research.parity.t9a_flood_tide import source_data_available

WEEKEND_ONLY = (MaskReason.WEEKEND_GAP,)

needs_data = pytest.mark.skipif(
    not source_data_available(),
    reason="seq=31 OHLC not present; set $QH_PARITY_DATA_DIR")


@pytest.fixture(scope="module")
def report():
    """One run, shared. It recomputes four E-Ratio reports over 124k bars."""
    if not source_data_available():
        pytest.skip("seq=31 OHLC not present; set $QH_PARITY_DATA_DIR")
    return m.check_mask_on(flags=WEEKEND_ONLY)


# -- the algebra, which needs no data --------------------------------------

def test_the_four_e_ratios_decompose_additively():
    """The three channels must sum to the total, or they are not a
    decomposition — they are three numbers next to a fourth."""
    c = m.ChannelResult(horizon=20, e_off=1.0, e_retained_old_atr=0.9,
                        e_retained_new_atr=1.2, e_on=1.15)
    assert c.removals == pytest.approx(-0.1)
    assert c.normaliser == pytest.approx(0.3)
    assert c.additions == pytest.approx(-0.05)
    assert c.total == pytest.approx(0.15)
    assert c.adds_up()


def test_the_normaliser_channel_holds_the_signal_set_fixed():
    """The spec's requirement, as an identity: both terms of the normaliser
    channel are measured on the retained set, so a change in which signals
    exist cannot leak into it."""
    c = m.ChannelResult(horizon=20, e_off=5.0, e_retained_old_atr=0.9,
                        e_retained_new_atr=0.9, e_on=99.0)
    assert c.normaliser == 0.0, (
        "same signals under two ATRs that happen to agree must give a zero "
        "normaliser channel regardless of what the other two terms do")


def test_the_mask_only_carries_the_flags_it_was_asked_for():
    idx = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    weekend_only = m.build_mask(idx, (MaskReason.WEEKEND_GAP,))
    assert not weekend_only.reason(MaskReason.ROLLOVER_WINDOW).any()
    both = m.build_mask(idx, m.FLAGS_APPLIED)
    assert both.reason(MaskReason.ROLLOVER_WINDOW).any(), (
        "a 200-hour span contains several rollovers; if none is flagged the "
        "flag is not being applied at all")


def test_a_recurring_daily_flag_starves_any_window_longer_than_a_day():
    """The structural finding, pinned so it cannot be rediscovered the hard way.

    R3 NaNs a WINDOW indicator whose lookback spans a masked bar. A flag that
    fires once a day therefore leaves clean runs of at most ~23 H1 bars, so a
    55-bar Donchian can essentially never be computed — the entry is
    annihilated by the interaction between the rule and the flag's period,
    not by anything about the data. Any WINDOW indicator with a lookback
    longer than the shortest recurring flag's period has this problem.
    """
    idx = pd.date_range("2024-01-01", periods=24 * 30, freq="h", tz="UTC")
    mask = m.build_mask(idx, (MaskReason.ROLLOVER_WINDOW,))
    tradable = mask.tradable.to_numpy()
    longest = best = 0
    for ok in tradable:
        best = best + 1 if ok else 0
        longest = max(longest, best)
    assert longest < 55, (
        f"longest clean run is {longest}; if this ever reaches 55 the "
        "annihilation finding no longer holds and the rollover configuration "
        "should be re-examined")


# -- the run ----------------------------------------------------------------

@needs_data
def test_mask_off_still_reproduces_seq_31(report):
    """The comparison is only meaningful if its baseline is the real one."""
    assert report.n_signals_off == 1669


@needs_data
def test_every_changed_signal_is_attributed(report):
    """Criterion 3 in one assertion."""
    assert report.unattributed == [], (
        f"{len(report.unattributed)} changed signals have no traceable cause; "
        f"first few: {report.unattributed[:5]}")
    assert report.fully_attributed


@needs_data
def test_the_attribution_counts_cover_every_changed_signal(report):
    """An empty unattributed bucket is worthless if the counts do not also
    account for the changes — a bug that silently dropped signals would
    satisfy the previous test."""
    for label, changed, counts in (
            ("lost", report.lost, report.attribution_lost),
            ("gained", report.gained, report.attribution_gained)):
        assert sum(counts.values()) >= len(changed), (
            f"{label}: {sum(counts.values())} attributions for "
            f"{len(changed)} changed signals")


@needs_data
def test_the_signal_set_really_did_change(report):
    """Guards against a mask that silently does nothing, which would make
    every other assertion here pass vacuously."""
    assert report.n_signals_on != report.n_signals_off
    assert report.lost, "no signals lost — is the mask reaching the indicators?"


@needs_data
def test_both_channels_are_non_zero_and_separable(report):
    """If either channel were always zero the split would be decoration."""
    assert any(c.removals != 0 for c in report.channels)
    assert any(c.normaliser != 0 for c in report.channels)


@needs_data
def test_the_decomposition_closes_at_every_horizon(report):
    for c in report.channels:
        assert c.adds_up(), (
            f"h={c.horizon}: removals {c.removals} + normaliser "
            f"{c.normaliser} + additions {c.additions} != total {c.total}")


@needs_data
def test_the_cooldown_cause_is_reported_separately_from_the_flags(report):
    """A signal explained by the cooldown is traced to the mask transitively,
    not directly, and the report must not blur the two — otherwise "attributed
    to weekend_gap" would cover changes no weekend gap goes near."""
    assert m.COOLDOWN_CAUSE in report.attribution_gained
    assert report.attribution_gained[m.COOLDOWN_CAUSE] > 0, (
        "the re-entry cooldown couples signals, so some gained signal should "
        "be downstream of a removed one; zero here means the coupling is not "
        "being modelled and those signals are being attributed to a flag that "
        "does not reach them")
    assert report.attribution_gained[MaskReason.WEEKEND_GAP.value] == 0, (
        "a gained signal cannot be caused directly by a weekend gap — the gap "
        "removes windows, it does not create them")


@needs_data
def test_the_report_serialises_with_its_flag_set(report):
    d = report.as_dict()
    assert d["flags_applied"] == [MaskReason.WEEKEND_GAP.value]
    assert d["mode"] == "mask_on"
    assert len(d["channels"]) == len(report.channels)


@needs_data
def test_logging_it_is_not_a_trial(tmp_path, report):
    from research import log as research_log
    research_log.register_hypothesis("seed", title="t", mechanism="m",
                                     log_dir=tmp_path)
    before = research_log.trial_count(tmp_path)
    entry = m.log_mask_on(report, log_dir=tmp_path)
    assert entry.counts_as_trial is False
    assert research_log.trial_count(tmp_path) == before
    ok, msg = research_log.verify(tmp_path)
    assert ok, msg
