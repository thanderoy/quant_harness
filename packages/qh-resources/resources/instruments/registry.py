"""T1 — instrument registry.

Loads a **pinned JSON snapshot committed to the repo**. No network call and no
MT5 call at import time, so a backtest run today and the same backtest run in a
year read identical contract specs. Snapshots are never overwritten, only
added; every artifact records which snapshot it used.

The load-bearing rule here is the provenance refusal. A hand-entered contract
spec is a seeded, unverified value of exactly the kind the log provenance audit
was built to catch — except this one propagates silently into every sizing
calculation downstream, where being wrong is expensive rather than merely
embarrassing. :meth:`Registry.load` therefore **raises** on a ``HAND_ENTERED``
snapshot unless ``allow_provisional=True`` is passed explicitly at the call
site, and anything loaded that way carries ``PROVISIONAL_SPECS`` so the stamp
reaches the artifact and the log entry rather than being remembered.

This converts "we'll pin the real specs later" from an intention into a
mechanical blocker.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

#: Directory holding the pinned snapshots. Never overwritten, only added to.
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

#: Stamp applied to anything loaded from a hand-entered snapshot.
PROVISIONAL_STAMP = "PROVISIONAL_SPECS"


class Provenance(str, Enum):
    """Where a contract spec came from. Two states, no default.

    There is deliberately no ``UNKNOWN``: a spec whose origin nobody recorded is
    the failure this field exists to make impossible, and offering a third value
    would let it be selected.
    """

    MT5_SYMBOL_INFO = "MT5_SYMBOL_INFO"
    HAND_ENTERED = "HAND_ENTERED"


class ProvisionalSpecError(RuntimeError):
    """A hand-entered snapshot was loaded without explicit opt-in."""


class UnknownInstrument(KeyError):
    """The registry holds no spec for this symbol.

    A distinct type so callers cannot conflate "no such instrument" with a
    missing dict key somewhere else in their own code.
    """


@dataclass(frozen=True)
class InstrumentSpec:
    """One instrument's contract terms, as pinned at ``as_of``.

    Field names follow the MT5 ``symbol_info`` struct so a D1 dump maps across
    without a translation layer inventing opportunities to transpose something.
    """

    symbol: str
    provenance: Provenance
    as_of_utc: str

    contract_size: float
    tick_size: float
    tick_value: float

    volume_min: float
    volume_max: float
    volume_step: float

    digits: int
    currency_profit: str   # quote currency — what P&L is denominated in
    currency_margin: str   # base currency

    trade_stops_level: int = 0
    trade_freeze_level: int = 0
    filling_mode: int | None = None
    swap_long: float | None = None
    swap_short: float | None = None
    swap_mode: int | None = None

    terminal_build: int | None = None
    notes: str = ""
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    # -- derived helpers ---------------------------------------------------

    def value_per_price_unit(self, lots: float = 1.0) -> float:
        """Account-of-quote-currency value of a 1.0 move in price, for ``lots``.

        Derived from ``contract_size``, not from ``tick_value``: tick_value is
        broker-reported in the *account* currency and silently embeds a
        conversion rate that was true when the spec was pulled. Using it here
        would bake a stale FX rate into every position size. Conversion is the
        caller's job, with a rate it supplies.
        """
        return lots * self.contract_size

    def round_to_lot_step(self, lots: float) -> float:
        """Round *down* to a valid lot, then clamp to [volume_min, volume_max].

        Rounds down, never to nearest: rounding up crosses the risk budget the
        caller just computed, and doing so silently is how a 2% intention
        becomes a 3% position.

        Returns 0.0 when the requested size is below ``volume_min`` — "cannot
        trade this small" is a real answer. Returning ``volume_min`` instead
        would be the min-lot clamp that lets realised risk exceed budget, which
        is precisely the D8 finding behind the h1_momentum halt: once lots pin
        at the minimum, the clamp stops bounding risk at all.
        """
        if not math.isfinite(lots) or lots <= 0:
            return 0.0
        step = self.volume_step
        if step <= 0:
            raise ValueError(f"{self.symbol}: volume_step must be > 0, got {step}")
        n = math.floor(round(lots / step, 9))
        sized = n * step
        # Re-round to the step's own decimal places; float division leaves
        # values like 0.30000000000000004 that fail an equality check later.
        sized = round(sized, _decimals(step))
        if sized < self.volume_min:
            return 0.0
        return min(sized, self.volume_max)

    def min_position_risk(self, stop_distance: float,
                          account_ccy_rate: float = 1.0) -> float:
        """Account-currency risk of the smallest position that can be opened.

        ``stop_distance`` is in price units. ``account_ccy_rate`` converts the
        quote currency to the account currency: pass 1.0 when they are the same.

        This is the number that decides tradability at a given equity, and it is
        a *floor* — it cannot be reduced by sizing, only by a tighter stop or a
        different instrument.
        """
        if stop_distance < 0:
            raise ValueError(f"stop_distance must be >= 0, got {stop_distance}")
        if account_ccy_rate <= 0:
            raise ValueError(
                f"account_ccy_rate must be > 0, got {account_ccy_rate}")
        units = self.volume_min * self.contract_size
        return units * stop_distance / account_ccy_rate

    @property
    def is_provisional(self) -> bool:
        return self.provenance is Provenance.HAND_ENTERED


def _decimals(step: float) -> int:
    """Decimal places implied by a lot step (0.01 -> 2)."""
    text = f"{step:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


@dataclass(frozen=True)
class Registry:
    """An immutable set of instrument specs loaded from one pinned snapshot."""

    snapshot: str
    as_of_utc: str
    specs: dict[str, InstrumentSpec]
    stamps: tuple[str, ...] = ()

    # -- construction ------------------------------------------------------

    @classmethod
    def load(cls, snapshot: str | Path, *,
             allow_provisional: bool = False) -> "Registry":
        """Load a pinned snapshot.

        Raises
        ------
        ProvisionalSpecError
            If any spec is ``HAND_ENTERED`` and ``allow_provisional`` is not
            explicitly True. The refusal is at the call site by design: opting
            in has to be visible in the code that did it, not buried in config.
        """
        path = Path(snapshot)
        if not path.is_absolute() and not path.exists():
            path = SNAPSHOT_DIR / path
        if not path.exists():
            raise FileNotFoundError(f"no such snapshot: {path}")

        payload = json.loads(path.read_text())
        specs: dict[str, InstrumentSpec] = {}
        for sym, body in payload["instruments"].items():
            specs[sym] = _spec_from_payload(sym, body, payload)

        provisional = sorted(s for s, v in specs.items() if v.is_provisional)
        if provisional and not allow_provisional:
            raise ProvisionalSpecError(
                f"{path.name} contains HAND_ENTERED specs for "
                f"{provisional}. These are unverified values that propagate "
                f"into every sizing calculation. Pass allow_provisional=True "
                f"explicitly to proceed; anything produced under one is "
                f"stamped {PROVISIONAL_STAMP} and may not be used for a parity "
                f"run, an acceptance criterion, or a logged research result."
            )

        stamps = tuple(payload.get("stamps", ()))
        if provisional and PROVISIONAL_STAMP not in stamps:
            stamps = stamps + (PROVISIONAL_STAMP,)

        return cls(
            snapshot=path.name,
            as_of_utc=payload["as_of_utc"],
            specs=specs,
            stamps=stamps,
        )

    # -- access ------------------------------------------------------------

    def __getitem__(self, symbol: str) -> InstrumentSpec:
        try:
            return self.specs[symbol]
        except KeyError:
            raise UnknownInstrument(
                f"{symbol!r} not in snapshot {self.snapshot!r}; "
                f"have {sorted(self.specs)}"
            ) from None

    def __contains__(self, symbol: object) -> bool:
        return symbol in self.specs

    def __iter__(self):
        return iter(self.specs)

    def __len__(self) -> int:
        return len(self.specs)

    @property
    def symbols(self) -> list[str]:
        return sorted(self.specs)

    @property
    def is_provisional(self) -> bool:
        return PROVISIONAL_STAMP in self.stamps

    def provenance_summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for spec in self.specs.values():
            out[spec.provenance.value] = out.get(spec.provenance.value, 0) + 1
        return out

    def artifact_metadata(self) -> dict:
        """Metadata every artifact produced under this registry must carry."""
        return {
            "registry_snapshot": self.snapshot,
            "registry_as_of_utc": self.as_of_utc,
            "registry_stamps": list(self.stamps),
            "registry_provenance": self.provenance_summary(),
        }


def _spec_from_payload(symbol: str, body: dict, envelope: dict) -> InstrumentSpec:
    prov = body.get("provenance", envelope.get("provenance"))
    if prov is None:
        raise ValueError(
            f"{symbol}: no provenance. There is no default — a spec whose "
            f"origin nobody recorded is the failure this field prevents."
        )
    known = {f for f in InstrumentSpec.__dataclass_fields__ if f != "raw"}
    kwargs = {k: v for k, v in body.items() if k in known}
    kwargs["symbol"] = symbol
    kwargs["provenance"] = Provenance(prov)
    kwargs.setdefault("as_of_utc", envelope["as_of_utc"])
    kwargs.setdefault("terminal_build", envelope.get("terminal_build"))
    return InstrumentSpec(**kwargs, raw=dict(body))
