"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_bars() -> pd.DataFrame:
    """500 days of synthetic OHLCV bars with a small upward drift."""
    rng = np.random.default_rng(42)
    n = 500
    ts = pd.date_range(end=datetime.now(UTC), periods=n, freq="D", tz="UTC")
    returns = rng.normal(0.0005, 0.012, size=n)
    close = 100.0 * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.001, n))
    high = np.maximum(close, open_) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(close, open_) * (1 - np.abs(rng.normal(0, 0.003, n)))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {
            "ts": ts,
            "symbol": "TEST",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "interval": "1d",
            "adjusted": True,
        }
    )


@pytest.fixture
def multi_symbol_bars(synthetic_bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Three symbols with offset drifts."""
    out: dict[str, pd.DataFrame] = {}
    rng = np.random.default_rng(7)
    for i, sym in enumerate(["AAA", "BBB", "CCC"]):
        df = synthetic_bars.copy()
        df["symbol"] = sym
        drift = (i - 1) * 0.0003  # AAA negative, BBB flat, CCC positive
        noise = rng.normal(drift, 0.005, len(df))
        df["close"] = df["close"] * np.exp(np.cumsum(noise))
        df["open"] = df["close"] * 0.999
        df["high"] = df[["open", "close"]].max(axis=1) * 1.002
        df["low"] = df[["open", "close"]].min(axis=1) * 0.998
        out[sym] = df.reset_index(drop=True)
    return out
