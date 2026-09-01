"""research.pre.normalizer_check — mechanical guard against algebraic contamination.

A feature and a target that share an input are related by algebra, not by the
market. At seq=69 forward |move| was normalised by ATR(14) while the feature
under test was ATR(14)/ATR(100); the resulting monotone "separation" of -1.049
ATR was pure division and was reported as a finding before being caught.

Call `assert_disjoint` at REGISTRATION time, not after reading a result.

>>> assert_disjoint(feature_inputs={"atr14", "atr100"},
...                 target_normalizer={"atr14"}, name="vol_ratio")
Traceback (most recent call last):
    ...
ContaminationError: vol_ratio shares {'atr14'} with its target's normalizer ...
"""
from __future__ import annotations


class ContaminationError(AssertionError):
    """Feature and target share an input; any relationship is algebraic."""


def assert_disjoint(feature_inputs: set[str], target_normalizer: set[str],
                    name: str = "feature") -> None:
    """Raise unless the feature's inputs and the target's normalizer are disjoint.

    Parameters
    ----------
    feature_inputs
        Every series the feature is computed from, e.g. {"atr14", "atr100"}.
    target_normalizer
        Every series the TARGET is divided by, e.g. {"atr14"} for a forward
        move expressed in ATR units. Pass an empty set for a raw-dollar target.
    """
    shared = set(feature_inputs) & set(target_normalizer)
    if shared:
        raise ContaminationError(
            f"{name} shares {shared} with its target's normalizer, so the two "
            f"are related by algebra rather than by the market. Either express "
            f"the target in raw units (dollars) or rebuild the feature without "
            f"{shared}."
        )
