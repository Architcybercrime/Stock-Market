"""Tests for the daemon's signal aggregator."""

from __future__ import annotations

import pandas as pd

from services.daemon.aggregator import SignalAggregator
from services.daemon.profiles import PROFILES, RiskProfileName
from services.daemon.strategies.base import StrategySignal


def _hist(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=len(prices), freq="B", tz="UTC"),
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1e6] * len(prices),
    })


def test_no_signals_no_orders():
    agg = SignalAggregator(PROFILES[RiskProfileName.CONSERVATIVE])
    out = agg.aggregate({}, {}, {}, {}, nav=100_000.0)
    assert out.orders == []
    assert out.selected == []


def test_high_confidence_signal_selected():
    agg = SignalAggregator(PROFILES[RiskProfileName.BALANCED])
    signals = {
        "AAPL": [
            StrategySignal("momentum", "AAPL", 0.8, 0.7, ""),
            StrategySignal("mean_reversion", "AAPL", 0.6, 0.7, ""),
            StrategySignal("ml", "AAPL", 0.5, 0.6, ""),
        ],
    }
    history = {"AAPL": _hist([100 + i for i in range(120)])}
    out = agg.aggregate(
        signals_by_symbol=signals,
        price_history=history,
        current_positions={},
        last_prices={"AAPL": 220.0},
        nav=100_000.0,
    )
    assert any(c.symbol == "AAPL" for c in out.selected)
    assert any(o.symbol == "AAPL" and o.side == "buy" for o in out.orders)


def test_low_confidence_signal_filtered():
    agg = SignalAggregator(PROFILES[RiskProfileName.CONSERVATIVE])
    signals = {
        "XYZ": [
            StrategySignal("momentum", "XYZ", 0.9, 0.3, ""),  # high score, low conf
        ],
    }
    history = {"XYZ": _hist([50] * 120)}
    out = agg.aggregate(signals, history, {}, {"XYZ": 50.0}, nav=100_000.0)
    assert "XYZ" not in out.target_weights
    assert all(o.symbol != "XYZ" for o in out.orders)


def test_position_cap_enforced():
    agg = SignalAggregator(PROFILES[RiskProfileName.CONSERVATIVE])
    p = PROFILES[RiskProfileName.CONSERVATIVE]
    # Single overwhelming signal — without cap, would consume all target_invested.
    signals = {
        "AAA": [StrategySignal("momentum", "AAA", 1.0, 0.9, "")],
    }
    history = {"AAA": _hist([100 + i for i in range(120)])}
    out = agg.aggregate(signals, history, {}, {"AAA": 200.0}, nav=100_000.0)
    if "AAA" in out.target_weights:
        assert out.target_weights["AAA"] <= p.max_position_pct + 1e-6


def test_zero_confidence_signal_does_not_drag_down_combined():
    """Regression: an ML signal returning conf=0 (no model registered) must NOT
    pull the combined confidence below profile.min_confidence and silently
    filter out otherwise-strong opinions from momentum + mean-reversion."""
    agg = SignalAggregator(PROFILES[RiskProfileName.CONSERVATIVE])
    signals = {
        "SBIN.NS": [
            StrategySignal("momentum", "SBIN.NS", 0.98, 0.80, "strong"),
            StrategySignal("mean_reversion", "SBIN.NS", 0.27, 0.55, "mild"),
            StrategySignal("ml", "SBIN.NS", 0.0, 0.0, "no model"),
        ],
    }
    history = {"SBIN.NS": _hist([100 + i for i in range(120)])}
    out = agg.aggregate(
        signals_by_symbol=signals,
        price_history=history,
        current_positions={},
        last_prices={"SBIN.NS": 800.0},
        nav=1_000_000.0,
    )
    # The zero-conf ML signal should be ignored in the confidence average.
    # mean(0.80, 0.55) = 0.675 which clears Conservative's 0.55 threshold.
    assert any(c.symbol == "SBIN.NS" for c in out.selected), (
        "SBIN should be selected — ML's conf=0 must not drag the average down"
    )


def test_opportunity_mode_deploys_more_with_stronger_signals():
    """Opportunity-adaptive mode should deploy MORE capital when many strong
    signals are present, and LESS when only marginal signals exist."""
    agg = SignalAggregator(PROFILES[RiskProfileName.OPPORTUNITY])

    history = {f"S{i}": _hist([100 + j for j in range(120)]) for i in range(10)}
    last_prices = {f"S{i}": 100.0 for i in range(10)}

    # 8 strong signals -> should deploy substantially
    strong_signals = {
        f"S{i}": [
            StrategySignal("momentum", f"S{i}", 0.95, 0.85, ""),
            StrategySignal("mean_reversion", f"S{i}", 0.40, 0.60, ""),
        ]
        for i in range(8)
    }
    strong = agg.aggregate(strong_signals, history, {}, last_prices, nav=1_000_000.0)
    strong_deployed = sum(strong.target_weights.values())

    # 2 marginal signals -> should deploy little
    marginal_signals = {
        f"S{i}": [
            StrategySignal("momentum", f"S{i}", 0.20, 0.55, ""),
            StrategySignal("mean_reversion", f"S{i}", 0.10, 0.55, ""),
        ]
        for i in range(2)
    }
    marginal = agg.aggregate(marginal_signals, history, {}, last_prices, nav=1_000_000.0)
    marginal_deployed = sum(marginal.target_weights.values())

    assert strong_deployed > marginal_deployed * 1.5, (
        f"opportunity mode should deploy more on stronger signals: "
        f"strong={strong_deployed:.3f} marginal={marginal_deployed:.3f}"
    )


def test_opportunity_mode_can_take_many_positions():
    """If 12 stocks all clear the quality bar, opportunity mode should take 12,
    not be capped at the conservative-style 5."""
    agg = SignalAggregator(PROFILES[RiskProfileName.OPPORTUNITY])
    history = {f"S{i}": _hist([100 + j for j in range(120)]) for i in range(12)}
    last_prices = {f"S{i}": 100.0 for i in range(12)}
    signals = {
        f"S{i}": [
            StrategySignal("momentum", f"S{i}", 0.90, 0.85, ""),
            StrategySignal("mean_reversion", f"S{i}", 0.50, 0.65, ""),
        ]
        for i in range(12)
    }
    out = agg.aggregate(signals, history, {}, last_prices, nav=1_000_000.0)
    assert len(out.selected) >= 10, (
        f"opportunity mode should pick many positions when many are strong, got {len(out.selected)}"
    )


def test_held_position_sold_when_signal_disappears():
    agg = SignalAggregator(PROFILES[RiskProfileName.BALANCED])
    # No signals at all -> any held positions should be sold.
    history = {"AAPL": _hist([180] * 120)}
    out = agg.aggregate(
        signals_by_symbol={},
        price_history=history,
        current_positions={"AAPL": 10.0},
        last_prices={"AAPL": 180.0},
        nav=100_000.0,
    )
    sells = [o for o in out.orders if o.side == "sell" and o.symbol == "AAPL"]
    assert sells, "expected a sell order for the held position"
