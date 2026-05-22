"""Alpaca broker stub.

Hard-gated behind LIVE_TRADING_ENABLED. The HTTP wiring is intentionally not
implemented in this scaffold — that would let a copy-paste accident send a
real order. Production should:

1. Install `alpaca-py`.
2. Implement submit/cancel/etc against the SDK.
3. Add reconciliation against the broker's order/position state on every poll.
4. Add explicit unit tests for idempotency under retries.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from libs.common.config import settings
from libs.common.types import Fill, Order
from services.execution.brokers.base import Broker, BrokerError


class AlpacaBroker(Broker):
    name = "alpaca"

    def __init__(self) -> None:
        if not settings.live_trading_enabled or settings.trading_mode != "live":
            raise BrokerError(
                "live trading disabled; refusing to instantiate AlpacaBroker. "
                "Set TRADING_MODE=live AND LIVE_TRADING_ENABLED=true in .env, "
                "and remove the KILL_SWITCH file, before constructing this."
            )
        if not (settings.alpaca_api_key and settings.alpaca_api_secret):
            raise BrokerError("alpaca credentials missing")
        # Real implementation:
        # from alpaca.trading.client import TradingClient
        # self._client = TradingClient(
        #     settings.alpaca_api_key.get_secret_value(),
        #     settings.alpaca_api_secret.get_secret_value(),
        #     paper=("paper" in settings.alpaca_base_url),
        # )
        raise NotImplementedError(
            "AlpacaBroker is a stub. Implement against alpaca-py before going live."
        )

    def submit(self, order: Order) -> Order:
        raise NotImplementedError

    def cancel(self, broker_order_id: str) -> None:
        raise NotImplementedError

    def get_order(self, broker_order_id: str) -> Order:
        raise NotImplementedError

    def list_open_orders(self) -> list[Order]:
        raise NotImplementedError

    def list_positions(self) -> dict[str, Decimal]:
        raise NotImplementedError

    def poll_fills(self, since: str | None = None) -> Iterable[Fill]:
        raise NotImplementedError
