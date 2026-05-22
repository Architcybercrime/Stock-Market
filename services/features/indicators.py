"""Leak-safe technical indicators.

Every function takes either a Series (close, typically) or a DataFrame with
OHLC columns and returns a Series indexed identically to the input. Rolling
windows use only data at or before the current bar; we never use `.shift(-k)`
to peek forward.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# Returns and volatility
# ----------------------------------------------------------------------

def returns(close: pd.Series, periods: int = 1) -> pd.Series:
    """Simple percentage returns over `periods` bars."""
    return close.pct_change(periods=periods)


def log_returns(close: pd.Series, periods: int = 1) -> pd.Series:
    """Log returns. Use these for additive aggregation and normality assumptions."""
    return np.log(close / close.shift(periods))


def realized_volatility(close: pd.Series, window: int = 20, annualization: int = 252) -> pd.Series:
    """Annualized realized volatility of log returns over a rolling window."""
    r = log_returns(close)
    return r.rolling(window).std() * np.sqrt(annualization)


# ----------------------------------------------------------------------
# Trend
# ----------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average. adjust=False matches the recursive definition."""
    return series.ewm(span=span, adjust=False).mean()


def momentum(close: pd.Series, window: int = 20) -> pd.Series:
    """Price momentum: ratio of current close to close `window` bars ago, minus 1."""
    return close / close.shift(window) - 1.0


# ----------------------------------------------------------------------
# Oscillators
# ----------------------------------------------------------------------

def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI. Uses EMA smoothing of gains and losses."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing: alpha = 1/window
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss > 0, 100.0)  # if no losses, RSI = 100
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Classic MACD: (EMA_fast - EMA_slow), signal, histogram."""
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist})


# ----------------------------------------------------------------------
# Bands and volatility envelopes
# ----------------------------------------------------------------------

def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: mid (SMA), upper, lower, %B, bandwidth."""
    mid = sma(close, window)
    std = close.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    # %B: position of close within the band; 0 = at lower, 1 = at upper
    pct_b = (close - lower) / (upper - lower)
    bandwidth = (upper - lower) / mid
    return pd.DataFrame({
        "bb_mid": mid,
        "bb_upper": upper,
        "bb_lower": lower,
        "bb_pct_b": pct_b,
        "bb_bandwidth": bandwidth,
    })


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range. df must have high, low, close columns."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


# ----------------------------------------------------------------------
# Normalization and risk helpers
# ----------------------------------------------------------------------

def zscore(series: pd.Series, window: int = 60) -> pd.Series:
    """Rolling z-score using only past `window` bars."""
    mu = series.rolling(window).mean()
    sigma = series.rolling(window).std()
    return (series - mu) / sigma


def drawdown(equity: pd.Series) -> pd.Series:
    """Peak-to-trough drawdown of an equity curve in the range [-1, 0]."""
    cummax = equity.cummax()
    return (equity / cummax) - 1.0
