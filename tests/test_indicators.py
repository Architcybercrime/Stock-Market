"""Tests for the indicator library: correctness + leak-safety."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.features import indicators


def test_returns_first_value_is_nan():
    s = pd.Series([100.0, 110.0, 121.0])
    r = indicators.returns(s)
    assert pd.isna(r.iloc[0])
    assert r.iloc[1] == pytest.approx(0.10)
    assert r.iloc[2] == pytest.approx(0.10)


def test_log_returns_additive():
    s = pd.Series([100.0, 110.0, 121.0])
    lr = indicators.log_returns(s).dropna()
    assert lr.sum() == pytest.approx(np.log(121.0 / 100.0))


def test_sma_only_uses_past():
    s = pd.Series(range(10), dtype=float)
    out = indicators.sma(s, window=3)
    # SMA at index 2 should be mean of [0, 1, 2] = 1
    assert out.iloc[2] == pytest.approx(1.0)
    # Replacing later values should not affect earlier SMA — proves no lookahead
    s2 = s.copy()
    s2.iloc[5:] = 999
    out2 = indicators.sma(s2, window=3)
    assert (out.iloc[:5] == out2.iloc[:5]).all() or (out.iloc[:5].fillna(0) == out2.iloc[:5].fillna(0)).all()


def test_rsi_bounds(synthetic_bars):
    r = indicators.rsi(synthetic_bars["close"], window=14).dropna()
    assert (r >= 0).all()
    assert (r <= 100).all()


def test_macd_components(synthetic_bars):
    out = indicators.macd(synthetic_bars["close"])
    assert {"macd", "macd_signal", "macd_hist"} <= set(out.columns)
    # hist should equal macd - signal
    diff = (out["macd"] - out["macd_signal"]).dropna()
    hist = out["macd_hist"].dropna()
    common = diff.index.intersection(hist.index)
    assert np.allclose(diff.loc[common], hist.loc[common])


def test_bollinger_pct_b_range(synthetic_bars):
    bb = indicators.bollinger_bands(synthetic_bars["close"])
    pct = bb["bb_pct_b"].dropna()
    # %B can technically go outside [0, 1] but very rarely; sanity range:
    assert pct.between(-1, 2).all()


def test_atr_positive(synthetic_bars):
    a = indicators.atr(synthetic_bars).dropna()
    assert (a > 0).all()


def test_zscore_centered(synthetic_bars):
    z = indicators.zscore(synthetic_bars["close"], window=60).dropna()
    # Long-run mean should be near zero for a roughly stationary z-score
    assert abs(z.mean()) < 1.0


def test_drawdown_nonpositive():
    equity = pd.Series([100, 110, 105, 120, 90, 130])
    dd = indicators.drawdown(equity)
    assert (dd <= 0).all()
    # Max DD should be (90-120)/120 = -0.25
    assert dd.min() == pytest.approx(-0.25)
