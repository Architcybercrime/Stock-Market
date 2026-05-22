"""Pre-trade risk checks.

Each check is a pure function of (order, portfolio_state, limits). The
sequence in `run_pre_trade_checks` is the order from RISK_POLICY.md.

If any check rejects, the order is dropped with a structured reason. The
signal that produced it is preserved upstream so attribution stays accurate.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from libs.common.logging import get_logger
from libs.common.types import Order, OrderSide
from services.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState
from services.risk.kill_switch import KillSwitch
from services.risk.limits import RiskLimitsConfig

log = get_logger(__name__)


@dataclass
class PortfolioState:
    """The slice of portfolio info the risk service needs."""

    nav: float
    cash: float
    positions_notional: dict[str, float]            # symbol -> current notional (signed)
    sector_notional: dict[str, float]               # sector -> current notional (abs)
    symbol_to_sector: dict[str, str] = field(default_factory=dict)


@dataclass
class RiskCheckResult:
    approved: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return not self.approved


# ----------------------------------------------------------------------
# Individual checks (pure)
# ----------------------------------------------------------------------

def kill_switch_check(_order: Order, _state: PortfolioState, _limits: RiskLimitsConfig,
                      *, kill_switch: KillSwitch) -> str | None:
    if kill_switch.is_engaged():
        return f"kill_switch_engaged: {kill_switch.reason}"
    return None


def circuit_breaker_check(_order: Order, _state: PortfolioState, _limits: RiskLimitsConfig,
                          *, breaker: CircuitBreaker) -> str | None:
    if breaker.state != CircuitBreakerState.OK:
        return f"circuit_breaker:{breaker.state.value}:{breaker.tripped_reason}"
    return None


def approved_symbol_check(order: Order, _state: PortfolioState, limits: RiskLimitsConfig) -> str | None:
    if limits.approved_symbols is None:
        return None
    if order.symbol not in limits.approved_symbols:
        return f"symbol_not_approved:{order.symbol}"
    return None


def order_size_check(order: Order, state: PortfolioState, limits: RiskLimitsConfig,
                     *, reference_price: float) -> str | None:
    notional = float(order.qty) * reference_price
    cap = state.nav * limits.max_order_notional_pct
    if notional > cap:
        return f"order_notional_exceeds_cap: notional={notional:.2f} cap={cap:.2f}"
    return None


def position_size_check(order: Order, state: PortfolioState, limits: RiskLimitsConfig,
                        *, reference_price: float) -> str | None:
    signed_qty = float(order.qty) if order.side == OrderSide.BUY else -float(order.qty)
    delta_notional = signed_qty * reference_price
    current = state.positions_notional.get(order.symbol, 0.0)
    resulting = current + delta_notional
    cap = state.nav * limits.max_position_pct
    if abs(resulting) > cap:
        return f"position_exceeds_cap: resulting={resulting:.2f} cap={cap:.2f}"
    return None


def sector_exposure_check(order: Order, state: PortfolioState, limits: RiskLimitsConfig,
                          *, reference_price: float) -> str | None:
    sector = state.symbol_to_sector.get(order.symbol)
    if not sector:
        return None
    signed_qty = float(order.qty) if order.side == OrderSide.BUY else -float(order.qty)
    delta = abs(signed_qty * reference_price)
    current = state.sector_notional.get(sector, 0.0)
    resulting = current + delta
    cap = state.nav * limits.max_sector_pct
    if resulting > cap:
        return f"sector_exceeds_cap: sector={sector} resulting={resulting:.2f} cap={cap:.2f}"
    return None


def leverage_check(order: Order, state: PortfolioState, limits: RiskLimitsConfig,
                   *, reference_price: float) -> str | None:
    signed_qty = float(order.qty) if order.side == OrderSide.BUY else -float(order.qty)
    delta_notional = signed_qty * reference_price
    new_positions = dict(state.positions_notional)
    new_positions[order.symbol] = new_positions.get(order.symbol, 0.0) + delta_notional
    gross = sum(abs(v) for v in new_positions.values())
    leverage = gross / max(state.nav, 1e-9)
    if leverage > limits.max_leverage:
        return f"leverage_exceeds: leverage={leverage:.3f} cap={limits.max_leverage:.3f}"
    return None


def cash_buffer_check(order: Order, state: PortfolioState, limits: RiskLimitsConfig,
                      *, reference_price: float) -> str | None:
    if order.side != OrderSide.BUY:
        return None
    cost = float(order.qty) * reference_price
    remaining_cash = state.cash - cost
    min_cash = state.nav * limits.min_cash_buffer_pct
    if remaining_cash < min_cash:
        return f"cash_buffer_violated: remaining={remaining_cash:.2f} min={min_cash:.2f}"
    return None


# ----------------------------------------------------------------------
# Rate limiter
# ----------------------------------------------------------------------

class RateLimiter:
    """Sliding-window order rate limiter."""

    def __init__(self, max_per_minute: int = 60) -> None:
        self.max_per_minute = max_per_minute
        self._times: deque[datetime] = deque()

    def check_and_record(self, ts: datetime | None = None) -> bool:
        """Return True if under limit; record timestamp regardless of outcome."""
        ts = ts or datetime.now(UTC)
        cutoff = ts - timedelta(minutes=1)
        while self._times and self._times[0] < cutoff:
            self._times.popleft()
        if len(self._times) >= self.max_per_minute:
            return False
        self._times.append(ts)
        return True


# ----------------------------------------------------------------------
# Top-level orchestrator
# ----------------------------------------------------------------------

def run_pre_trade_checks(
    order: Order,
    state: PortfolioState,
    limits: RiskLimitsConfig,
    *,
    kill_switch: KillSwitch,
    breaker: CircuitBreaker,
    rate_limiter: RateLimiter,
    reference_price: float,
) -> RiskCheckResult:
    """Run all checks in policy order. Stops on first failure with a reason.

    A single rejection is enough; we do not aggregate multiple failures because
    each check protects a different invariant and the first failing one is the
    one we want to debug.
    """
    reasons: list[str] = []

    pipeline = [
        ("kill_switch", lambda: kill_switch_check(order, state, limits, kill_switch=kill_switch)),
        ("circuit_breaker", lambda: circuit_breaker_check(order, state, limits, breaker=breaker)),
        ("approved_symbol", lambda: approved_symbol_check(order, state, limits)),
        ("order_size", lambda: order_size_check(order, state, limits, reference_price=reference_price)),
        ("position_size", lambda: position_size_check(order, state, limits, reference_price=reference_price)),
        ("sector_exposure", lambda: sector_exposure_check(order, state, limits, reference_price=reference_price)),
        ("leverage", lambda: leverage_check(order, state, limits, reference_price=reference_price)),
        ("cash_buffer", lambda: cash_buffer_check(order, state, limits, reference_price=reference_price)),
    ]

    for name, check_fn in pipeline:
        reason = check_fn()
        if reason:
            log.warning("risk.reject", check=name, order_id=order.id, symbol=order.symbol, reason=reason)
            reasons.append(f"{name}: {reason}")
            return RiskCheckResult(approved=False, reasons=reasons)

    # Rate limit is last because it has a side effect (records the order).
    if not rate_limiter.check_and_record():
        reason = f"rate_limit_exceeded: max={limits.max_orders_per_minute}/min"
        log.warning("risk.reject", check="rate_limit", order_id=order.id, symbol=order.symbol, reason=reason)
        return RiskCheckResult(approved=False, reasons=[f"rate_limit: {reason}"])

    return RiskCheckResult(approved=True, reasons=[])
