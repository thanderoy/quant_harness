"""H1 intraday-momentum paper-forward (research log seq=59/60/61/62/65).

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is a DATA-COLLECTION deployment, not a promoted strategy. The rule is the
only effect in this research programme that beat a permutation null twice
(p=0.010 at seq=65, p=0.005 at seq=71, both against nulls that carry gold's
drift). What it has never done is clear the recoverability test: the nested
selection procedure that would have DISCOVERED it fails at p=0.105. The honest
summary is "real, but not findable by anything we built".

Forward data is the only evidence that is not contaminated by selection, and
none has ever been collected. That is the entire purpose of running this.

FROZEN RULE -- do not tune. Any change requires a new research registration.
    entry   long when the causal percentile of intraday_ret >= 0.90
    hold    exactly 12 H1 bars, then exit at market
    side    long only; no short, no re-entry while open
    target  none

TWO DEVIATIONS FROM THE RESEARCH RULE, both measured before deployment:
  1. CATASTROPHIC STOP at 10 x ATR(14). The research rule has no stop, which is
     not acceptable on a live connection. Measured over the 1,991 historical
     trades: median adverse excursion 1.29 ATR, p99 7.98, maximum 13.59. A
     10-ATR stop would have bound 0.301% of the time (6 trades). Fidelity is
     preserved to 99.7%; it is a disaster guard, not a parameter.
  2. BOUNDED PERCENTILE WINDOW. Research used an expanding percentile over the
     full 21-year series; live can only fetch a bounded window. At 50,000 bars
     the entry decision agrees with the full-history decision 99.70% of the
     time (99.21% even at 10,000).

CAPACITY LIMIT, stated because it governs whether this can ever go live.
Minimum lot is 0.01 = 1 oz. With a 10-ATR stop and H1 ATR(14) currently
~$14-22/oz, one minimum lot risks $141-220. On the $3,643 demo that is 3.9-6.0%
of balance -- at the risk ceiling with NO room to size down, since the ATR
sizer already asks for 0.0129 lots and gets floored to 0.01. On the $100 target
account the same position would risk 141-220% of the account. THIS RULE IS
UNTRADEABLE AT $100 REGARDLESS OF WHETHER THE EDGE IS REAL.

TIMEZONE. MT5 returns broker server time (MetaQuotes EET/EEST, UTC+2/+3), not
UTC. `intraday_ret` is measured from the session's first bar, so mislabelling
the clock shifts every session boundary and changes which bar is "day open" --
the exact defect found at research seq=48. Timestamps are localised to
Europe/Athens and converted to UTC before the day grouping, matching the
research pipeline.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.adapters.mt5_api import MT5APIClient
from app.adapters.broker import MT5Broker
from resources.execution.broker import OrderRequest
from resources.side import Side
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings
from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.sizer import size_order

SHORT_NAME = "H1M"
SYMBOL = "XAUUSD"
TIMEFRAME = "H1"
MAGIC_NUMBER = 1600001

# --- frozen research parameters ------------------------------------------
ENTRY_PCTILE = 0.90
HOLD_BARS = 12
ATR_LEN = 14
# --- deployment-only parameters, measured in the docstring ----------------
STOP_ATR_MULT = 10.0
PCTILE_LOOKBACK = 50_000
RISK_PCT = 0.05

SERVER_TZ = "Europe/Athens"


class H1MomentumStrategy(BaseStrategy):
    """Long-only intraday momentum on XAUUSD H1, fixed 12-bar hold."""

    SHORT_NAME = SHORT_NAME

    def __init__(self, environment: str = "test",
                 magic_number: int = MAGIC_NUMBER) -> None:
        super().__init__(environment=environment)
        self.magic_number = magic_number
        self.mt5_client = MT5APIClient(
            base_url=settings.get_mt5_url(self.environment)
        )

    # ------------------------------------------------------------------ data
    def _fetch_candles(self, count: int = PCTILE_LOOKBACK) -> Optional[pd.DataFrame]:
        """H1 OHLC indexed in UTC. Returns None on any failure."""
        try:
            data = self.mt5_client.get_market_rates(SYMBOL, TIMEFRAME, count=count)
        except Exception:
            self.logger.exception("h1_momentum.fetch_failed")
            return None
        rates = (data or {}).get("rates") or []
        if len(rates) < 2_000:
            self.logger.warning(
                "h1_momentum.insufficient_history bars=%s", len(rates)
            )
            return None
        df = pd.DataFrame(rates)
        ts = pd.to_datetime(df["time"])
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(
                SERVER_TZ, ambiguous=False, nonexistent="shift_forward"
            )
        df.index = ts.dt.tz_convert("UTC")
        df = df[["open", "high", "low", "close"]].astype(float).sort_index()
        return df[~df.index.duplicated(keep="last")]

    @staticmethod
    def _atr(df: pd.DataFrame, n: int = ATR_LEN) -> pd.Series:
        """Wilder ATR, identical to research.pre.feature_screen._atr."""
        pc = df.close.shift(1)
        tr = pd.concat(
            [df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1
        ).max(axis=1)
        return tr.ewm(alpha=1 / n, adjust=False).mean()

    @staticmethod
    def _intraday_ret(df: pd.DataFrame, atr: pd.Series) -> pd.Series:
        """Return since the session's first bar, normalised by ATR."""
        day = df.index.normalize()
        day_open = df.open.groupby(day).transform("first")
        return (df.close / day_open - 1.0) / (atr / df.close)

    # ---------------------------------------------------------------- signal
    def _generate_signal(self, df: pd.DataFrame) -> tuple[Optional[str], float, float]:
        """Evaluate the LAST CLOSED bar (iloc[-2]). Never iloc[-1]."""
        atr = self._atr(df)
        v = self._intraday_ret(df, atr)
        closed = v.iloc[:-1]                       # drop the forming bar
        if len(closed) < 2_000 or not pd.notna(closed.iloc[-1]):
            return None, float("nan"), float("nan")
        current = float(closed.iloc[-1])
        history = closed.iloc[:-1].dropna()
        pct = float((history < current).mean())
        atr_now = float(atr.iloc[-2])
        self.logger.info(
            "h1_momentum.signal bar=%s intraday_ret=%.4f pctile=%.4f atr=%.2f n_hist=%d",
            closed.index[-1].isoformat(), current, pct, atr_now, len(history),
        )
        if pct >= ENTRY_PCTILE:
            return "BUY", pct, atr_now
        return None, pct, atr_now

    # ------------------------------------------------------------- positions
    def _open_positions(self) -> list[dict]:
        try:
            return self.mt5_client.get_open_positions(
                magic=self.magic_number, symbol=SYMBOL
            ) or []
        except Exception:
            self.logger.exception("h1_momentum.positions_fetch_failed")
            return []

    def manage_positions(self, df: pd.DataFrame) -> None:
        """Close anything that has been held HOLD_BARS closed bars.

        Age is counted in BARS present in the series, not wall-clock hours, so
        weekends and broker gaps do not shorten or lengthen the hold.
        """
        for pos in self._open_positions():
            ticket = pos.get("ticket")
            opened = pos.get("time")
            if ticket is None or opened is None:
                continue
            try:
                ts = pd.to_datetime(opened)
                if ts.tz is None:
                    ts = ts.tz_localize(
                        SERVER_TZ, ambiguous=False, nonexistent="shift_forward"
                    )
                ts = ts.tz_convert("UTC")
            except Exception:
                self.logger.exception("h1_momentum.bad_position_time ticket=%s", ticket)
                continue
            bars_held = int((df.index > ts).sum()) - 1     # exclude forming bar
            if bars_held < HOLD_BARS:
                self.logger.info(
                    "h1_momentum.holding ticket=%s bars=%d/%d", ticket,
                    bars_held, HOLD_BARS,
                )
                continue
            try:
                res = self.mt5_client.close_position(
                    ticket=int(ticket), magic=self.magic_number, comment="H1M-exit"
                )
                ok = bool(res and res.get("success"))
                self.logger.info(
                    "h1_momentum.exit ticket=%s bars=%d success=%s retcode=%s %s",
                    ticket, bars_held, ok,
                    (res or {}).get("retcode"),
                    (res or {}).get("retcode_description"),
                )
            except Exception:
                self.logger.exception("h1_momentum.exit_failed ticket=%s", ticket)

    # ----------------------------------------------------------------- entry
    def _place_order(self, lot: float, sl: float, atr_now: float, pct: float,
                     login: Optional[int]) -> None:
        """Send the market order and record it. Every outcome is logged."""
        try:
            order = MT5Broker(self.mt5_client).submit(OrderRequest(
                symbol=SYMBOL, side=Side.LONG, volume=lot,
                sl=sl, magic=self.magic_number, comment="H1M",
            ))
        except Exception:
            self.logger.exception("h1_momentum.order_exception")
            return

        if not (order and order.get("success") is True):
            self.logger.error(
                "h1_momentum.order_failed retcode=%s %s order=%s",
                (order or {}).get("retcode"),
                (order or {}).get("retcode_description"), order,
            )
            return

        fill = float(order.get("price", 0.0))
        self.logger.info(
            "h1_momentum.order_filled ticket=%s fill=%.2f volume=%s sl=%.2f "
            "atr=%.2f pctile=%.4f",
            order.get("ticket") or order.get("order"), fill, lot, sl, atr_now, pct,
        )
        try:
            account_instance = None
            if login is not None:
                from app.trades.models import Account

                account_instance = Account.objects.filter(login=login).first()
            create_trade_record(
                order,
                symbol=SYMBOL,
                direction="BUY",
                entry_price=fill,
                order_volume=lot,
                account=account_instance,
                market_type="COMMODITIES",
                strategy=self.__class__.__name__,
                timeframe="1H",
                sl=sl,
                tp=None,
                environment=self.environment,
            )
        except Exception:
            self.logger.exception("h1_momentum.trade_record_failed")

    # ------------------------------------------------------------- lifecycle
    def evaluate(self) -> Optional[str]:
        """One scheduled pass: manage exits first, then consider an entry."""
        self.logger.info(
            "h1_momentum.start env=%s mt5=%s magic=%s",
            self.environment, settings.get_mt5_url(self.environment),
            self.magic_number,
        )
        df = self._fetch_candles()
        if df is None:
            return None

        self.manage_positions(df)

        if self._open_positions():
            self.logger.info("h1_momentum.skip reason=position_open")
            return None

        signal, pct, atr_now = self._generate_signal(df)
        if signal is None:
            return None
        try:
            info = self.mt5_client.get_account_info() or {}
            balance = float(info.get("balance") or 0.0)
            login = info.get("login")
        except Exception:
            self.logger.exception("h1_momentum.account_fetch_failed")
            return None
        if balance <= 0:
            self.logger.error("h1_momentum.bad_balance balance=%s", balance)
            return None

        sized = size_order(
            SYMBOL, account_balance=balance, atr_value=atr_now,
            risk_pct=RISK_PCT, sl_atr_multiplier=STOP_ATR_MULT,
        )
        if not sized.tradable:
            self.logger.warning(
                "h1_momentum.sizer_declined reason=%s balance=%s atr=%s",
                sized.reason.value, balance, atr_now)
            return None
        lot, effective_atr = sized.lots, sized.effective_atr
        try:
            tick = self.mt5_client.get_tick(SYMBOL) or {}
            ask = float(tick.get("ask") or 0.0)
        except Exception:
            self.logger.exception("h1_momentum.tick_failed")
            return None
        if ask <= 0:
            self.logger.error("h1_momentum.bad_tick ask=%s", ask)
            return None

        sl = ask - STOP_ATR_MULT * effective_atr
        risk_pct_actual = (STOP_ATR_MULT * effective_atr * lot * 100.0) / balance
        self.logger.info(
            "h1_momentum.sizing balance=%.2f lot=%.2f eff_atr=%.2f stop_dist=%.2f "
            "implied_risk_pct=%.3f",
            balance, lot, effective_atr, STOP_ATR_MULT * effective_atr,
            risk_pct_actual,
        )
        self._place_order(lot, sl, atr_now, pct, login)
        return signal
