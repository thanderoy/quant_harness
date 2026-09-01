"""research.pre.decisive_stream — force the decisive statistic to be declared.

A test that emits several statistics has several possible verdicts, and picking
among them after seeing the numbers is not a test. This has been missed twice:

    seq=65  fixed p=0.010  vs  nested p=0.105     -> streams disagreed
    seq=71  gated p=0.005  vs  advantage p=0.0647 -> streams disagreed

Both were resolved against the preferred reading by arguing from the
registration's prose. That worked, but it relied on the prose happening to be
clear enough. Declare the stream instead.

>>> d = declare("advantage", 0.05, {"gated", "ungated", "advantage"},
...             rationale="the claim is that the GATE adds something; `gated` "
...                       "is confounded with the base signal working")
>>> d.verdict({"gated": 0.005, "advantage": 0.0647})
('FAIL', 'advantage p=0.0647 >= 0.05')
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisiveStream:
    name: str
    threshold: float
    rationale: str

    def verdict(self, p_values: dict[str, float]) -> tuple[str, str]:
        """Apply the pre-declared rule. Ignores every non-decisive stream."""
        if self.name not in p_values:
            raise KeyError(
                f"decisive stream {self.name!r} absent from results "
                f"{sorted(p_values)}; the run did not measure what was declared."
            )
        p = p_values[self.name]
        ok = p < self.threshold
        return ("PASS" if ok else "FAIL",
                f"{self.name} p={p:.4g} {'<' if ok else '>='} {self.threshold}")


def declare(name: str, threshold: float, available: set[str],
            rationale: str) -> DecisiveStream:
    """Declare which statistic decides. Call at REGISTRATION time.

    `rationale` is required and must be non-trivial: if the reason cannot be
    stated before the run, the choice is not yet principled.
    """
    if name not in available:
        raise ValueError(f"{name!r} is not one of the emitted streams {sorted(available)}")
    if not 0.0 < threshold < 1.0:
        raise ValueError(f"threshold must be in (0,1); got {threshold}")
    if len(rationale.strip()) < 20:
        raise ValueError("rationale must say WHY this stream decides, before results exist")
    return DecisiveStream(name, threshold, rationale.strip())
