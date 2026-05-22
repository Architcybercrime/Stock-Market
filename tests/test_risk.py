"""Tests for the risk service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from libs.common.types import Order, OrderSide
from services.risk.checks import (
    PortfolioState,
    RateLimiter,
    cash_buffer_check,
    leverage_check,
    position_size_check,
    run_pre_trade_checks,
)
from services.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState
from services.risk.kill_switch import KillSwitch
from services.risk.limits import RiskLimitsConfig


def _make_order(symbol: str = "AAPL", qty: float = 100, side: OrderSide = OrderSide.BUY) -> Order:
    return Order(
        strategy="test",
        symbol=symbol,
        side=side,
        qty=Decimal(str(qty)),
        created_at=datetime.now(UTC),
    )


def test_position_size_check_rejects_oversize():
    state = PortfolioState(nav=100_000, cash=100_000, positions_notional={}, sector_notional={})
    limits = RiskLimitsConfig(max_position_pct=0.05)  # cap = $5000
    order = _make_order(qty=200)  # 200 * $100 = $20000 > cap
    reason = position_size_check(order, state, limits, reference_price=100.0)
    assert reason is not None
    assert "position_exceeds_cap" in reason


def test_leverage_check_rejects_overleverage():
    # $100k NAV, $80k already deployed; new $50k buy pushes gross to $130k = 1.3x
    state = PortfolioState(
        nav=100_000,
        cash=20_000,
        positions_notional={"MSFT": 80_000.0},
        sector_notional={},
    )
    limits = RiskLimitsConfig(max_leverage=1.0)
    order = _make_order(symbol="AAPL", qty=500)  # 500 * $100 = $50k
    reason = leverage_check(order, state, limits, reference_price=100.0)
    assert reason is not None
    assert "leverage_exceeds" in reason


def test_cash_buffer_check():
    state = PortfolioState(nav=100_000, cash=10_000, positions_notional={}, sector_notional={})
    limits = RiskLimitsConfig(min_cash_buffer_pct=0.05)  # min $5000
    # Buying $9000 worth would leave $1000 < $5000 buffer
    order = _make_order(qty=90)
    reason = cash_buffer_check(order, state, limits, reference_price=100.0)
    assert reason is not None


def test_kill_switch_blocks_all_orders(tmp_path: Path):
    ks = KillSwitch(tmp_path / "KILL")
    ks.engage(reason="drill", actor="test")
    breaker = CircuitBreaker(max_daily_loss_pct=0.02, max_drawdown_pct=0.10)
    state = PortfolioState(nav=100_000, cash=100_000, positions_notional={}, sector_notional={})
    limits = RiskLimitsConfig()
    rl = RateLimiter()
    order = _make_order()
    result = run_pre_trade_checks(
        order, state, limits, kill_switch=ks, breaker=breaker, rate_limiter=rl, reference_price=100.0
    )
    assert result.rejected
    assert any("kill_switch" in r for r in result.reasons)


def test_circuit_breaker_trips_on_drawdown():
    breaker = CircuitBreaker(max_daily_loss_pct=0.10, max_drawdown_pct=0.10)
    now = datetime.now(UTC)
    breaker.update(equity=100_000.0, ts=now)
    breaker.update(equity=110_000.0, ts=now)  # peak
    breaker.update(equity=98_000.0, ts=now)   # -10.9% from peak
    assert breaker.state == CircuitBreakerState.DRAWDOWN_TRIPPED


def test_circuit_breaker_stays_tripped():
    breaker = CircuitBreaker(max_daily_loss_pct=0.10, max_drawdown_pct=0.10)
    now = datetime.now(UTC)
    breaker.update(equity=100_000.0, ts=now)
    breaker.update(equity=110_000.0, ts=now)
    breaker.update(equity=98_000.0, ts=now)
    # Even if equity recovers, breaker stays tripped until reset
    breaker.update(equity=150_000.0, ts=now)
    assert breaker.state != CircuitBreakerState.OK


def test_rate_limiter_blocks_burst():
    rl = RateLimiter(max_per_minute=3)
    assert rl.check_and_record()
    assert rl.check_and_record()
    assert rl.check_and_record()
    assert not rl.check_and_record()
