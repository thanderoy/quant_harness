"""
btpy_ebb_n_flow.py — Bollinger mean-reversion (regime-gated) backtest harness for XAUUSD.

Diversifier against the trend/breakout book. Fades band excursions ONLY in balanced
regimes (low Kaufman Efficiency Ratio); stands aside in trends. TP = midline, SL = ATR
beyond entry, hard time-stop. R:R>=1 is relaxed to a runtime R-floor + a post-hoc
breakeven-WR gate (required_WR = 1 / (1 + avg_R)).

Conventions (per WMPS project context):
  - All-hours bars in; session filter applied INSIDE next(), not via pre-filtered data.
  - Closed-candle discipline: backtesting.py's next() already sees only the closed bar
    and fills at the next open (no look-ahead). The live MT5 port must use df.iloc[-2].
  - Position sizing mirrors sizer.py: risk_pct off SL distance, ATR floor, lot clamp.

Usage:
    pip install backtesting pandas numpy
    python btpy_ebb_n_flow.py --csv XAUUSD_M15.csv --tf M15
    python btpy_ebb_n_flow.py --csv XAUUSD_M30.csv --tf M30 --spread-mult 2.0

CSV: a datetime column (UTC) + Open, High, Low, Close, Volume (case-insensitive).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

# --- XAUUSD / Pepperstone constants -----------------------------------------
XAUUSD_CONTRACT = 100.0    # oz per 1.0 lot  (0.01 lot = 1 oz)
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
DOLLARS_PER_OZ_PER_LOT = XAUUSD_CONTRACT  # $ PnL per $1/oz move per 1.0 lot

# Round-trip cost in basis points of notional (commission + raw spread), split per side.
# Razor gold ~ $0.37 round trip / 0.01 lot on ~$2000 notional ~= 1.85 bps round trip.
DEFAULT_COST_BPS_ROUNDTRIP = 1.85

# --- Per-timeframe defaults --------------------------------------------------
@dataclass(frozen=True)
class TFConfig:
    time_stop_bars: int
    leverage: float


TF_DEFAULTS = {
    "M15": TFConfig(time_stop_bars=8, leverage=100.0),
    "M30": TFConfig(time_stop_bars=6, leverage=100.0),
}


# --- Pure indicator functions (NaN-padded, same length as input) ------------
def bollinger(close: np.ndarray, n: int, k: float):
    s = pd.Series(close)
    mid = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return mid.to_numpy(), (mid + k * sd).to_numpy(), (mid - k * sd).to_numpy()


def kaufman_er(close: np.ndarray, n: int) -> np.ndarray:
    """|net change over n| / sum of |bar-to-bar change| over n. ->1 trend, ->0 chop."""
    s = pd.Series(close)
    direction = s.diff(n).abs()
    volatility = s.diff().abs().rolling(n).sum()
    er = direction / volatility.replace(0.0, np.nan)
    return er.to_numpy()


def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    """Wilder's ATR (RMA of True Range) — matches Pine ta.atr()."""
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return atr.to_numpy()


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.to_numpy()


# --- Strategy ----------------------------------------------------------------
class EbbNFlow(Strategy):
    # Bollinger
    bb_n = 20
    bb_k = 2.0
    # Regime gate
    er_n = 10
    er_max = 0.30
    # ATR / risk
    atr_n = 14
    atr_floor = 1.0          # $/oz floor so low-vol regimes can't explode size
    sl_atr_mult = 1.0        # SL distance = sl_atr_mult * max(ATR, floor) beyond entry
    atr_spike_mult = 2.5     # reject if current TR > this * ATR (likely trend/news bar)
    min_r = 0.5              # runtime R-floor (relaxed R:R>=1 rule)
    risk_pct = 0.01
    # Exits / session
    time_stop_bars = 8
    session_start = 8        # UTC inclusive
    session_end = 17         # UTC exclusive
    friday_cutoff = 14       # no new entries after this hour UTC on Friday

    def init(self):
        c, h, l = self.data.Close, self.data.High, self.data.Low
        self.mid, self.upper, self.lower = self.I(
            bollinger, c, self.bb_n, self.bb_k
        )
        self.er = self.I(kaufman_er, c, self.er_n)
        self.atr = self.I(atr_wilder, h, l, c, self.atr_n)
        self.tr = self.I(true_range, h, l, c)

    def _in_session(self, ts: pd.Timestamp) -> bool:
        if ts.weekday() > 4:  # Sat/Sun
            return False
        if not (self.session_start <= ts.hour < self.session_end):
            return False
        if ts.weekday() == 4 and ts.hour >= self.friday_cutoff:
            return False
        return True

    @staticmethod
    def _news_block(ts: pd.Timestamp) -> bool:
        # Placeholder. Live port reuses the asqs high-impact-gold-news filter.
        return False

    def _size_oz(self, sl_dist: float) -> int:
        """Risk-based sizing mirroring sizer.py; returns integer oz (units for backtesting.py)."""
        risk_amount = self.equity * self.risk_pct
        sl_dist = max(sl_dist, self.sl_atr_mult * self.atr_floor)
        lots = risk_amount / (sl_dist * DOLLARS_PER_OZ_PER_LOT)
        lots = float(np.clip(lots, XAUUSD_MIN_LOT, XAUUSD_MAX_LOT))
        return max(1, int(round(lots * XAUUSD_CONTRACT)))

    def next(self):
        i = len(self.data) - 1          # current (closed) bar
        ts = self.data.index[i]

        # Time-stop on any open position.
        for trade in list(self.trades):
            if i - trade.entry_bar >= self.time_stop_bars:
                trade.close()

        if self.position:               # one position per variant
            return
        if not self._in_session(ts) or self._news_block(ts):
            return

        atr = self.atr[-1]
        er = self.er[-1]
        if np.isnan(atr) or np.isnan(er) or np.isnan(self.mid[-1]):
            return
        if er >= self.er_max:            # regime gate: only fade in chop
            return
        if self.tr[-1] > self.atr_spike_mult * atr:   # spike = likely trend/news
            return

        close = self.data.Close[-1]
        mid = self.mid[-1]
        sl_dist = self.sl_atr_mult * max(atr, self.atr_floor)

        # SELL: fade an up-excursion back to the mean.
        if close > self.upper[-1]:
            tp = mid
            sl = close + sl_dist
            tp_dist, sl_d = close - tp, sl - close
            if tp_dist > 0 and sl_d > 0 and (tp_dist / sl_d) >= self.min_r:
                self.sell(size=self._size_oz(sl_d), sl=sl, tp=tp)

        # BUY: fade a down-excursion back to the mean.
        elif close < self.lower[-1]:
            tp = mid
            sl = close - sl_dist
            tp_dist, sl_d = tp - close, close - sl
            if tp_dist > 0 and sl_d > 0 and (tp_dist / sl_d) >= self.min_r:
                self.buy(size=self._size_oz(sl_d), sl=sl, tp=tp)


# --- Data loading ------------------------------------------------------------
def load_ohlcv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    dt_col = next((cols[k] for k in ("time", "datetime", "date", "timestamp") if k in cols), None)
    if dt_col is None:
        raise ValueError("CSV needs a time/datetime/date/timestamp column.")
    df.index = pd.to_datetime(df[dt_col], utc=True).dt.tz_localize(None)
    rename = {}
    for want in ("open", "high", "low", "close", "volume"):
        if want in cols:
            rename[cols[want]] = want.capitalize()
    df = df.rename(columns=rename)
    need = ["Open", "High", "Low", "Close"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    return df[["Open", "High", "Low", "Close", "Volume"]].sort_index()


# --- Reporting: the relaxed-R:R safeguard -----------------------------------
def breakeven_wr_report(bt_stats) -> None:
    trades = bt_stats._trades
    if trades is None or len(trades) == 0:
        print("\n[WR gate] No trades — nothing to evaluate.")
        return

    wins = (trades["PnL"] > 0).sum()
    n = len(trades)
    realized_wr = wins / n

    # avg_R from actual exits: |reward leg| / |risk leg| per trade, using entry/sl/tp intent.
    # Approximate avg_R from realized win/loss magnitudes (robust to partials/time-stops).
    avg_win = trades.loc[trades["PnL"] > 0, "PnL"].mean()
    avg_loss = abs(trades.loc[trades["PnL"] < 0, "PnL"].mean())
    avg_r = (avg_win / avg_loss) if (avg_loss and not np.isnan(avg_loss)) else float("nan")
    breakeven_wr = 1.0 / (1.0 + avg_r) if avg_r and not np.isnan(avg_r) else float("nan")

    print("\n--- Relaxed-R:R safeguard (breakeven-WR gate) ---")
    print(f"  trades:            {n}")
    print(f"  realized WR:       {realized_wr:6.2%}")
    print(f"  avg realized R:    {avg_r:6.3f}  (avg_win / avg_loss)")
    print(f"  breakeven WR:      {breakeven_wr:6.2%}  = 1 / (1 + avg_R)")
    if not np.isnan(breakeven_wr):
        margin = realized_wr - breakeven_wr
        verdict = "PASS" if margin > 0.05 else ("THIN" if margin > 0 else "FAIL")
        print(f"  margin:            {margin:+6.2%}  -> {verdict}")
        print("  (PASS wants comfortable margin; THIN/FAIL means WR can't cover the lower R.)")


def main() -> None:
    ap = argparse.ArgumentParser(description="ebb_n_flow Bollinger mean-reversion backtest")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--tf", choices=list(TF_DEFAULTS), default="M15")
    ap.add_argument("--cash", type=float, default=100.0)
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS_ROUNDTRIP,
                    help="Round-trip cost in bps of notional (commission + raw spread).")
    ap.add_argument("--spread-mult", type=float, default=1.0,
                    help="Spread stress multiplier (run 1.5 and 2.0 per pipeline).")
    ap.add_argument("--equity-out", default=None, help="Save equity curve CSV (for correlation overlay).")
    args = ap.parse_args()

    cfg = TF_DEFAULTS[args.tf]
    data = load_ohlcv(args.csv)

    # backtesting.py commission is a per-side fraction of trade value.
    commission = (args.cost_bps / 1e4 / 2.0) * args.spread_mult

    bt = Backtest(
        data,
        EbbNFlow,
        cash=args.cash,
        commission=commission,
        margin=1.0 / cfg.leverage,
        trade_on_close=False,   # fill next open -> no look-ahead
        exclusive_orders=True,
    )
    stats = bt.run(time_stop_bars=cfg.time_stop_bars)

    print(f"\n=== ebb_n_flow {args.tf} | spread x{args.spread_mult} | cost {args.cost_bps}bps RT ===")
    print(stats)
    breakeven_wr_report(stats)

    print("\nNEXT: re-run at --spread-mult 1.5 and 2.0, then overlay the equity curve "
          "against crest_n_keel H1 and asqs and compute return correlation (the deployment gate).")

    if args.equity_out:
        stats._equity_curve[["Equity"]].to_csv(args.equity_out)
        print(f"Equity curve written to {args.equity_out}")


if __name__ == "__main__":
    main()

