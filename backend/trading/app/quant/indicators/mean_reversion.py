import pandas as pd
import numpy as np
from typing import Optional

def mean_reversion(data: pd.DataFrame, window: int = 20, num_std_dev: float = 2.0) -> pd.DataFrame:
    """
    Compute Bollinger Bands and simple mean-reversion signals.

    Returns a copy of the input DataFrame with the following added columns:
      - bollinger_mean
      - bollinger_upper
      - bollinger_lower
      - mr_signal:  1 -> long signal, -1 -> short signal, 0 -> no signal

    Notes:
    - Uses a one-bar shift to avoid lookahead: breaches are detected on the previous bar.
    - Caller should handle warm-up NaNs produced by rolling calculations.
    """
    if 'close' not in data.columns:
        raise ValueError("DataFrame must contain a 'close' column")

    df = data.copy()

    # rolling mean/std; require full window to compute values (min_periods=window)
    df['bollinger_mean'] = df['close'].rolling(window=window, min_periods=window).mean()
    df['bollinger_std'] = df['close'].rolling(window=window, min_periods=window).std(ddof=0)

    # avoid zero-std issues
    df['bollinger_std'].replace(0, np.nan, inplace=True)

    df['bollinger_upper'] = df['bollinger_mean'] + num_std_dev * df['bollinger_std']
    df['bollinger_lower'] = df['bollinger_mean'] - num_std_dev * df['bollinger_std']

    # Use previous bar values for breach detection to prevent lookahead
    prev_close = df['close'].shift(1)
    prev_upper = df['bollinger_upper'].shift(1)
    prev_lower = df['bollinger_lower'].shift(1)

    prev_breach_long = prev_close < prev_lower
    prev_breach_short = prev_close > prev_upper

    # Require some reversion attempt on current bar for confirmation
    long_signal = prev_breach_long & (df['close'] >= df['bollinger_lower'])
    short_signal = prev_breach_short & (df['close'] <= df['bollinger_upper'])

    df['mr_signal'] = 0
    df.loc[long_signal.fillna(False), 'mr_signal'] = 1
    df.loc[short_signal.fillna(False), 'mr_signal'] = -1

    # make signal column small dtype
    df['mr_signal'] = df['mr_signal'].astype('int8')

    # optional: remove intermediate std column
    df.drop(columns=['bollinger_std'], inplace=True)

    return df
