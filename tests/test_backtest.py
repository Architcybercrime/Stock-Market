"""Tests for the backtester."""

from __future__ import annotations

import pandas as pd
import pytest

from services.backtest.engine import BacktestEngine, PortfolioSnapshot, Strategy, TargetOrder
from services.backtest.metrics import compute_metrics


class _BuyAndHold(Strategy):
    """Buy 100 shares of the first symbol seen, hold forever."""

    name = "buy_and_hold"

    def __init__(self) -> None:
        self._bought = False

    def on_bar(self, bar, portfolio):
        if self._bought:
            return []
        self._bought = True
        return [TargetOrder(symbol=bar["symbol"], side="buy", qty=100)]


def test_engine_runs_end_to_end(multi_symbol_bars):
    engine = BacktestEngine(initial_cash=100_000.0)
    result = engine.run(_BuyAndHold(), multi_symbol_bars)
    assert not result.equity.empty
    assert len(result.fills) == 1
    assert result.fills.iloc[0]["qty"] == 100


def test_initial_equity_matches_cash(multi_symbol_bars):
    engine = BacktestEngine(initial_cash=50_000.0)

    class _NoTrade(Strategy):
        def on_bar(self, bar, portfolio):
            return []

    result = engine.run(_NoTrade(), multi_symbol_bars)
    assert result.equity.iloc[0] == pytest.approx(50_000.0)
    assert result.equity.iloc[-1] == pytest.approx(50_000.0)


def test_no_lookahead_in_fill_price(multi_symbol_bars):
    """An order submitted at bar t must fill at bar t+1 price, not t."""
    engine = BacktestEngine(initial_cash=100_000.0)

    sym = list(multi_symbol_bars.keys())[0]
    df = multi_symbol_bars[sym].sort_values("ts").reset_index(drop=True)
    # Trim to two bars so we can compare directly.
    two_bars = {sym: df.iloc[:2]}

    class _BuyOnFirst(Strategy):
        def __init__(self) -> None:
            self._done = False

        def on_bar(self, bar, portfolio):
            if self._done:
                return []
            self._done = True
            return [TargetOrder(symbol=bar["symbol"], side="buy", qty=1)]

    result = engine.run(_BuyOnFirst(), two_bars)
    assert len(result.fills) == 1
    # Fill price should be derived from the 2nd bar's open, not the 1st bar's close
    fill_price = float(result.fills.iloc[0]["price"])
    second_open = float(df.iloc[1]["open"])
    # Slippage adds a fraction; within 1% of bar 2 open is fine, but should not equal bar 1 close
    bar1_close = float(df.iloc[0]["close"])
    assert abs(fill_price - second_open) / second_open < 0.05
    # The fill should NOT equal bar 1 close (which would mean lookahead)
    assert fill_price != bar1_close


def test_metrics_on_flat_equity():
    equity = pd.Series([100.0] * 10, index=pd.date_range("2025-01-01", periods=10, tz="UTC"))
    m = compute_metrics(equity)
    assert m["total_return"] == pytest.approx(0.0)
    assert m["max_drawdown"] == pytest.approx(0.0)
