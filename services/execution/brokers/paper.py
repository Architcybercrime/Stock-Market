"""In-process paper broker.

Fills orders against a mark price provided by the caller. Applies the same
SlippageModel and CostModel used in backtests so paper and backtested
strategies stay comparable.

Idempotency: keyed on `client_order_id`. Re-submitting the same id returns
the existing order.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from libs.common.logging import get_logger
from libs.common.types import Fill, Order, OrderSide, OrderStatus
from services.backtest.costs import CostModel, SlippageModel
from services.execution.brokers.base import Broker, BrokerError

log = get_logger(__name__)


class PaperBroker(Broker):
    name = "paper"

    def __init__(
        self,
        get_price: callable,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> None:
        self.get_price = get_price            # symbol -> current price float
        self.cost_model = cost_model or CostModel()
        self.slippage_model = slippage_model or SlippageModel()
        self._orders: dict[str, Order] = {}
        self._client_to_id: dict[str, str] = {}
        self._fills: list[Fill] = []
        self._positions: dict[str, Decimal] = {}

    def submit(self, order: Order) -> Order:
        # Idempotency
        if order.client_order_id in self._client_to_id:
            existing_id = self._client_to_id[order.client_order_id]
            return self._orders[existing_id]

        price = self._get_price_or_raise(order.symbol)
        is_buy = order.side == OrderSide.BUY

        fill_price = self.slippage_model.apply(price, float(order.qty), adv=None, is_buy=is_buy)
        notional = float(order.qty) * fill_price
        fee = self.cost_model.fee(notional, is_sell=not is_buy)

        # Mark order filled in one shot for simplicity. Real paper trading
        # with partial fills would step through the order book; out of scope.
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = Decimal(str(fill_price))

        fill = Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=Decimal(str(fill_price)),
            fee=Decimal(str(fee)),
            venue=self.name,
            ts=datetime.now(UTC),
        )

        self._orders[order.id] = order
        self._client_to_id[order.client_order_id] = order.id
        self._fills.append(fill)
        signed = order.qty if is_buy else -order.qty
        self._positions[order.symbol] = self._positions.get(order.symbol, Decimal(0)) + signed

        log.info(
            "paper.fill",
            symbol=order.symbol,
            side=order.side.value,
            qty=str(order.qty),
            price=fill_price,
            fee=fee,
        )
        return order

    def cancel(self, broker_order_id: str) -> None:
        order = self._orders.get(broker_order_id)
        if not order:
            raise BrokerError(f"unknown order id: {broker_order_id}")
        if order.status not in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
            return
        order.status = OrderStatus.CANCELLED

    def get_order(self, broker_order_id: str) -> Order:
        if broker_order_id not in self._orders:
            raise BrokerError(f"unknown order id: {broker_order_id}")
        return self._orders[broker_order_id]

    def list_open_orders(self) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
        ]

    def list_positions(self) -> dict[str, Decimal]:
        return {k: v for k, v in self._positions.items() if v != 0}

    def poll_fills(self, since: str | None = None) -> Iterable[Fill]:
        if since is None:
            return list(self._fills)
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        return [f for f in self._fills if f.ts > cutoff]

    def _get_price_or_raise(self, symbol: str) -> float:
        try:
            price = float(self.get_price(symbol))
        except Exception as exc:
            raise BrokerError(f"price unavailable for {symbol}") from exc
        if price <= 0 or not (price == price):  # NaN check
            raise BrokerError(f"invalid price for {symbol}: {price}")
        return price
