"""Order Management System.

Sits between the strategy and the broker. Owns:
- The order state machine.
- Pre-trade risk gating (delegates to services.risk).
- Idempotent submission (we never resubmit an order we already submitted).
- Audit logging of every transition.

The OMS is single-threaded by design. Concurrent strategies should each get
their own OMS instance keyed by strategy id; a single global OMS makes
reasoning about state races painful and we'd rather avoid that until we need it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from libs.common.logging import get_logger
from libs.common.types import Fill, Order, OrderStatus
from services.execution.brokers.base import Broker, BrokerError
from services.risk.checks import (
    PortfolioState,
    RateLimiter,
    RiskCheckResult,
    run_pre_trade_checks,
)
from services.risk.circuit_breaker import CircuitBreaker
from services.risk.kill_switch import KillSwitch
from services.risk.limits import RiskLimitsConfig

log = get_logger(__name__)


class OMS:
    def __init__(
        self,
        broker: Broker,
        limits: RiskLimitsConfig,
        kill_switch: KillSwitch,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        self.broker = broker
        self.limits = limits
        self.kill_switch = kill_switch
        self.breaker = circuit_breaker
        self.rate_limiter = RateLimiter(limits.max_orders_per_minute)
        self._orders: dict[str, Order] = {}
        self._fills_by_order: dict[str, list[Fill]] = {}

    # ------------------------------------------------------------------ submission

    def submit(
        self,
        order: Order,
        portfolio_state: PortfolioState,
        reference_price: float,
    ) -> Order:
        """Risk-check and submit an order. Returns the updated Order."""
        # Idempotency guard at the OMS layer too — even if the broker is also
        # idempotent, we never want to double-charge fees on a retry.
        if order.client_order_id in {o.client_order_id for o in self._orders.values()}:
            existing = next(o for o in self._orders.values() if o.client_order_id == order.client_order_id)
            log.info("oms.duplicate_submit_ignored", client_order_id=order.client_order_id)
            return existing

        risk: RiskCheckResult = run_pre_trade_checks(
            order=order,
            state=portfolio_state,
            limits=self.limits,
            kill_switch=self.kill_switch,
            breaker=self.breaker,
            rate_limiter=self.rate_limiter,
            reference_price=reference_price,
        )

        if risk.rejected:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "; ".join(risk.reasons)
            self._orders[order.id] = order
            log.warning(
                "oms.rejected",
                order_id=order.id,
                symbol=order.symbol,
                reasons=risk.reasons,
            )
            return order

        order.status = OrderStatus.PENDING
        self._orders[order.id] = order

        try:
            order = self.broker.submit(order)
            order.status = OrderStatus.SUBMITTED if order.status == OrderStatus.PENDING else order.status
            self._orders[order.id] = order
            log.info(
                "oms.submitted",
                order_id=order.id,
                broker=self.broker.name,
                symbol=order.symbol,
                side=order.side.value,
                qty=str(order.qty),
            )
        except BrokerError as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"broker_error: {exc}"
            self._orders[order.id] = order
            log.error("oms.broker_error", order_id=order.id, error=str(exc))

        return order

    # ------------------------------------------------------------------ cancel

    def cancel(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if not order:
            raise KeyError(order_id)
        self.broker.cancel(order_id)
        order.status = OrderStatus.CANCELLED
        self._orders[order_id] = order
        log.info("oms.cancelled", order_id=order_id)
        return order

    # ------------------------------------------------------------------ reconcile

    def reconcile_fills(self, since: str | None = None) -> list[Fill]:
        """Pull fills from broker and update internal order state. Idempotent."""
        new_fills: list[Fill] = []
        seen_ids = {f.id for fills in self._fills_by_order.values() for f in fills}
        for f in self.broker.poll_fills(since):
            if f.id in seen_ids:
                continue
            new_fills.append(f)
            self._fills_by_order.setdefault(f.order_id, []).append(f)
            order = self._orders.get(f.order_id)
            if order:
                order.filled_qty += f.qty
                if order.filled_qty >= order.qty:
                    order.status = OrderStatus.FILLED
                else:
                    order.status = OrderStatus.PARTIALLY_FILLED
        return new_fills

    def open_orders(self) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
        ]

    def all_orders(self) -> list[Order]:
        return list(self._orders.values())
