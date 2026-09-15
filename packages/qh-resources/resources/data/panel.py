"""T3 — aligned multi-instrument OHLCV, with a mask per instrument.

A panel is where the symbol-agnostic core stops being a claim. Once several
instruments share one index, every question that used to be implicit for a
single-instrument system has to be answered out loud: what does a bar mean for
EURUSD at an hour when only XAUUSD was quoting, and what does a strategy see
when it asks for that bar's close?

The answers here are the spec's, and they are deliberately unhelpful to the
convenient case:

**Union index.** The panel spans every timestamp any instrument printed. An
intersection would be quietly lossy — one instrument with a data outage would
delete those hours for all the others, and the deletion would look like a
market closure rather than a gap in one file.

**No forward-fill across a closed session.** A bar that does not exist for an
instrument is *masked*, never synthesised. This is the rule that costs the
most and matters the most. Carrying the last close forward produces a series
that looks continuous, prices at which nothing could have been done, and
returns of exactly zero that a correlation or a volatility estimate will treat
as real information. The zero-return runs are the dangerous part: they deflate
realised volatility and pull pairwise correlation toward whatever the overlap
happens to be, which is precisely the number D4 exists to measure.

**A masked bar reads as NaN.** Not a stale price, and not the underlying value
with a flag beside it that a caller may forget to check. The accessors here
apply the mask; ``raw()`` is the single, named way to see through it, so
reading an untradable price is something a call site has to say it is doing.

The per-instrument mask combines two things: absence (this instrument did not
print this bar) and any ``TradabilityMask`` the caller supplies (rollover,
weekend gap, spread blowout). Absence is attributed to ``SESSION_CLOSED`` --
the instrument was not quoting when others were.
"""

from __future__ import annotations

import pandas as pd

from .mask import MaskReason, TradabilityMask

#: Columns a frame must carry to enter a panel. ``volume`` is optional because
#: FX volume from MT5 is tick count, not traded size, and is absent or
#: meaningless often enough that requiring it would exclude good data.
REQUIRED_COLUMNS = ("open", "high", "low", "close")

OPTIONAL_COLUMNS = ("volume", "spread")


class PanelAlignmentError(ValueError):
    """A frame cannot be placed on the panel index."""


def _validate(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise PanelAlignmentError(f"{symbol}: index must be a DatetimeIndex")
    if df.index.tz is None:
        raise PanelAlignmentError(
            f"{symbol}: index must be timezone-aware. A naive index assumes a "
            "timezone silently, and aligning two instruments under different "
            "silent assumptions is the failure this class exists to prevent"
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise PanelAlignmentError(f"{symbol}: missing columns {missing}")
    if not df.index.is_monotonic_increasing:
        raise PanelAlignmentError(f"{symbol}: index is not sorted")
    if df.index.has_duplicates:
        n = int(df.index.duplicated().sum())
        raise PanelAlignmentError(f"{symbol}: {n} duplicate timestamps")
    return df.tz_convert("UTC")


class Panel:
    """Multi-instrument OHLCV on one UTC index, with a mask per instrument.

    ``Panel({"EURUSD": df1, "XAUUSD": df2})`` aligns both onto the union of
    their indices. Where an instrument has no bar the values are NaN and the
    mask is False, attributed to ``SESSION_CLOSED``.
    """

    def __init__(self, frames: dict[str, pd.DataFrame],
                 masks: dict[str, TradabilityMask] | None = None) -> None:
        if not frames:
            raise PanelAlignmentError("a panel needs at least one instrument")

        validated = {sym: _validate(sym, df) for sym, df in frames.items()}

        index = None
        for df in validated.values():
            index = df.index if index is None else index.union(df.index)
        self.index: pd.DatetimeIndex = index.sort_values()

        self._frames: dict[str, pd.DataFrame] = {}
        self._masks: dict[str, TradabilityMask] = {}
        self._present: dict[str, pd.Series] = {}

        supplied = masks or {}
        for sym, df in validated.items():
            cols = [c for c in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)
                    if c in df.columns]
            # reindex, never reindex(method="ffill") — see the module docstring.
            self._frames[sym] = df[cols].reindex(self.index)
            present = pd.Series(self.index.isin(df.index), index=self.index)
            self._present[sym] = present
            self._masks[sym] = self._build_mask(sym, present, supplied.get(sym))

    # -- construction helpers ---------------------------------------------

    def _build_mask(self, symbol: str, present: pd.Series,
                    supplied: TradabilityMask | None) -> TradabilityMask:
        """Absence, plus whatever the caller already knew about this symbol.

        The supplied mask is re-flagged onto the panel index rather than
        assumed to share it: it was almost certainly built on the
        instrument's own index, which is shorter.
        """
        mask = TradabilityMask(self.index)
        mask.flag(MaskReason.SESSION_CLOSED, ~present)
        if supplied is not None:
            for reason in MaskReason:
                flagged = supplied.reason(reason)
                if flagged.any():
                    mask.flag(reason, flagged.reindex(self.index,
                                                      fill_value=False))
        return mask

    # -- access ------------------------------------------------------------

    @property
    def symbols(self) -> list[str]:
        return list(self._frames)

    def __len__(self) -> int:
        return len(self.index)

    def __contains__(self, symbol: object) -> bool:
        return symbol in self._frames

    def mask(self, symbol: str) -> TradabilityMask:
        self._require(symbol)
        return self._masks[symbol]

    def present(self, symbol: str) -> pd.Series:
        """True where the instrument actually printed a bar.

        Distinct from tradability: a bar can exist and still be masked for
        rollover or spread. Reported separately so a panel with 40% masked
        bars can be diagnosed as a data gap or as a filter doing its job.
        """
        self._require(symbol)
        return self._present[symbol]

    def raw(self, symbol: str) -> pd.DataFrame:
        """The aligned frame with the mask **not** applied.

        For diagnostics and for parity work that has to see what was in the
        file. A strategy that calls this is opting out of R3 in writing.
        """
        self._require(symbol)
        return self._frames[symbol].copy()

    def ohlcv(self, symbol: str) -> pd.DataFrame:
        """The aligned frame with masked bars NaN across every column."""
        self._require(symbol)
        return self._frames[symbol].where(self._masks[symbol].tradable, other=pd.NA)

    def series(self, symbol: str, field: str = "close") -> pd.Series:
        """One masked column for one instrument."""
        self._require(symbol)
        frame = self._frames[symbol]
        if field not in frame.columns:
            raise KeyError(f"{symbol} has no column {field!r}")
        return frame[field].where(self._masks[symbol].tradable)

    def field(self, field: str = "close") -> pd.DataFrame:
        """One masked column for every instrument, symbols as columns.

        The shape a correlation or a panel regression wants. Because masked
        bars are NaN rather than filled, ``.dropna()`` on the result gives
        the bars on which every instrument was genuinely tradable -- which is
        the honest denominator for a cross-instrument statistic.
        """
        return pd.DataFrame(
            {sym: self.series(sym, field) for sym in self._frames},
            index=self.index)

    @property
    def tradable(self) -> pd.DataFrame:
        return pd.DataFrame(
            {sym: m.tradable for sym, m in self._masks.items()},
            index=self.index)

    def summary(self) -> dict:
        return {
            "n_bars": len(self.index),
            "start_utc": self.index[0].isoformat(),
            "end_utc": self.index[-1].isoformat(),
            "symbols": self.symbols,
            "per_symbol": {
                sym: {"n_present": int(self._present[sym].sum()),
                      **self._masks[sym].summary()}
                for sym in self._frames
            },
            "n_bars_tradable_for_all": int(self.tradable.all(axis=1).sum()),
            "alignment": "union index; absent bars masked, never forward-filled",
        }

    def _require(self, symbol: str) -> None:
        if symbol not in self._frames:
            raise KeyError(
                f"{symbol!r} is not in this panel: {self.symbols}")
