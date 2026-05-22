"""Broker abstraction. Live brokers and the paper broker implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from decimal import Decimal

from libs.common.types import Fill, Order


class BrokerError(Exception):
    """Raised when the broker rejects or fails an operation."""


class Broker(ABC):
    name: str = "base"

    @abstractmethod
    def submit(self, order: Order) -> Order:
        """Submit an order. Returns the order with status updated.

        Must be idempotent on `client_order_id`: submitting the same client id
        twice returns the existing broker order, not a new one.
        """

    @abstractmethod
    def cancel(self, broker_order_id: str) -> None: ...

    @abstractmethod
    def get_order(self, broker_order_id: str) -> Order: ...

    @abstractmethod
    def list_open_orders(self) -> list[Order]: ...

    @abstractmethod
    def list_positions(self) -> dict[str, Decimal]:
        """Symbol -> qty held at the broker."""

    @abstractmethod
    def poll_fills(self, since: str | None = None) -> Iterable[Fill]:
        """Return new fills since `since` (broker-specific cursor)."""
