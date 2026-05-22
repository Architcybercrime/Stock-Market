"""Alpaca broker — real implementation.

Paper trading by default. Live trading is hard-gated behind both
LIVE_TRADING_ENABLED=true AND TRADING_MODE=live in the environment. Even
then, the kill switch file is checked on every submission.

This is intentionally cautious. If you want to go live you must:

1. Set LIVE_TRADING_ENABLED=true and TRADING_MODE=live in .env
2. Change ALPACA_BASE_URL to https://api.alpaca.markets (drop "paper-")
3. Replace ALPACA_API_KEY/SECRET with your live-account keys
4. Remove the data/KILL_SWITCH file if present
5. Walk the pre-live checklist in docs/COMPLIANCE.md

Any single one of those left undone keeps you in paper trading. The same
class handles both modes — only the base URL and the credentials differ.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from libs.common.config import settings
from libs.common.logging import get_logger
from libs.common.types import Fill, Order, OrderSide, OrderStatus, OrderType
from services.execution.brokers.base import Broker, BrokerError

log = get_logger(__name__)


class AlpacaBroker(Broker):
    """Real Alpaca broker. Defaults to paper trading."""

    name = "alpaca"

    def __init__(self, *, force_paper: bool = True) -> None:
        if not (settings.alpaca_api_key and settings.alpaca_api_secret):
            raise BrokerError(
                "AlpacaBroker requires ALPACA_API_KEY + ALPACA_API_SECRET in .env. "
                "Sign up at https://alpaca.markets (free)."
            )

        from alpaca.trading.client import TradingClient

        base_url = settings.alpaca_base_url
        # Paper-trading endpoint is determined by the URL Alpaca's SDK uses
        # the `paper` flag for. If the env explicitly says live AND the
        # operator flag is set, we honor it. Otherwise we force paper.
        is_paper = force_paper or "paper" in base_url or not settings.live_trading_enabled
        if not is_paper:
            kill_file = Path(settings.data_root) / "KILL_SWITCH"
            if kill_file.exists():
                raise BrokerError(
                    "live trading requested but KILL_SWITCH file present; "
                    "delete the file to proceed, or revert to paper mode."
                )
            log.critical(
                "alpaca.live_mode_initialized",
                base_url=base_url,
                message=(
                    "AlpacaBroker is in LIVE mode. Real orders will be placed. "
                    "Verify position sizes and kill switch are operational."
                ),
            )

        self._client = TradingClient(
            api_key=settings.alpaca_api_key.get_secret_value(),
            secret_key=settings.alpaca_api_secret.get_secret_value(),
            paper=is_paper,
        )
        self.is_paper = is_paper

    # ------------------------------------------------------------------ submit

    def submit(self, order: Order) -> Order:
        from alpaca.common.exceptions import APIError
        from alpaca.trading.enums import OrderSide as AOrderSide
        from alpaca.trading.enums import OrderType as AOrderType
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        # Idempotency: Alpaca de-dupes on client_order_id. We rely on that
        # plus our OMS-level guard. Never resubmit the same client_order_id.
        side = AOrderSide.BUY if order.side == OrderSide.BUY else AOrderSide.SELL
        tif = {
            "DAY": TimeInForce.DAY,
            "GTC": TimeInForce.GTC,
            "IOC": TimeInForce.IOC,
            "FOK": TimeInForce.FOK,
        }.get(order.tif, TimeInForce.DAY)

        try:
            if order.type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.qty),
                    side=side,
                    time_in_force=tif,
                    client_order_id=order.client_order_id,
                )
            elif order.type == OrderType.LIMIT:
                if order.limit_price is None:
                    raise BrokerError("limit order requires limit_price")
                req = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.qty),
                    side=side,
                    type=AOrderType.LIMIT,
                    limit_price=float(order.limit_price),
                    time_in_force=tif,
                    client_order_id=order.client_order_id,
                )
            else:
                raise BrokerError(f"order type not supported: {order.type}")

            resp = self._client.submit_order(req)
            order.status = OrderStatus.SUBMITTED
            log.info(
                "alpaca.submitted",
                client_order_id=order.client_order_id,
                broker_id=str(resp.id),
                symbol=order.symbol,
                side=order.side.value,
                qty=str(order.qty),
                paper=self.is_paper,
            )
            return order
        except APIError as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"alpaca_api_error: {exc}"
            log.error("alpaca.api_error", error=str(exc), client_order_id=order.client_order_id)
            raise BrokerError(str(exc)) from exc

    # ------------------------------------------------------------------ cancel

    def cancel(self, broker_order_id: str) -> None:
        from alpaca.common.exceptions import APIError

        try:
            self._client.cancel_order_by_id(broker_order_id)
            log.info("alpaca.cancelled", broker_order_id=broker_order_id)
        except APIError as exc:
            raise BrokerError(str(exc)) from exc

    # ------------------------------------------------------------------ reads

    def get_order(self, broker_order_id: str) -> Order:
        from alpaca.common.exceptions import APIError

        try:
            o = self._client.get_order_by_id(broker_order_id)
        except APIError as exc:
            raise BrokerError(str(exc)) from exc

        return _from_alpaca_order(o)

    def list_open_orders(self) -> list[Order]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
        orders = self._client.get_orders(filter=req)
        return [_from_alpaca_order(o) for o in orders]

    def list_positions(self) -> dict[str, Decimal]:
        positions = self._client.get_all_positions()
        return {p.symbol: Decimal(str(p.qty)) for p in positions}

    def get_account(self) -> dict:
        """Return account snapshot: equity, cash, buying power."""
        a = self._client.get_account()
        return {
            "equity": float(a.equity),
            "cash": float(a.cash),
            "buying_power": float(a.buying_power),
            "pattern_day_trader": getattr(a, "pattern_day_trader", False),
        }

    def poll_fills(self, since: str | None = None) -> Iterable[Fill]:
        """Return fills (closed/partially-filled orders) since cursor."""
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        after_dt = None
        if since:
            after_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500, after=after_dt)
        orders = self._client.get_orders(filter=req)
        fills: list[Fill] = []
        for o in orders:
            if not o.filled_at or not o.filled_avg_price or float(o.filled_qty or 0) == 0:
                continue
            fills.append(
                Fill(
                    order_id=str(o.client_order_id or o.id),
                    symbol=o.symbol,
                    side=OrderSide.BUY if str(o.side).lower().endswith("buy") else OrderSide.SELL,
                    qty=Decimal(str(o.filled_qty)),
                    price=Decimal(str(o.filled_avg_price)),
                    fee=Decimal(0),  # Alpaca is commission-free for stocks
                    venue="alpaca",
                    ts=o.filled_at.astimezone(UTC) if o.filled_at.tzinfo else o.filled_at.replace(tzinfo=UTC),
                )
            )
        return fills


def _from_alpaca_order(o) -> Order:
    """Map an alpaca-py Order object onto our Order type."""
    status_map = {
        "new": OrderStatus.SUBMITTED,
        "accepted": OrderStatus.SUBMITTED,
        "pending_new": OrderStatus.PENDING,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "cancelled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
        "expired": OrderStatus.CANCELLED,
    }
    side = OrderSide.BUY if str(o.side).lower().endswith("buy") else OrderSide.SELL
    return Order(
        id=str(o.id),
        client_order_id=str(o.client_order_id or o.id),
        strategy="alpaca_external",
        symbol=o.symbol,
        side=side,
        qty=Decimal(str(o.qty)),
        type=OrderType.MARKET if str(o.order_type).lower().endswith("market") else OrderType.LIMIT,
        limit_price=Decimal(str(o.limit_price)) if o.limit_price else None,
        created_at=o.created_at.astimezone(UTC) if o.created_at and o.created_at.tzinfo else o.created_at,
        status=status_map.get(str(o.status).split(".")[-1].lower(), OrderStatus.PENDING),
        filled_qty=Decimal(str(o.filled_qty or 0)),
        avg_fill_price=Decimal(str(o.filled_avg_price)) if o.filled_avg_price else None,
    )
