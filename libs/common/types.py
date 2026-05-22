"""Shared domain types used across services.

Kept deliberately small. New types should live next to the service that owns
them; only put it here if multiple unrelated services need it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"            # accepted by OMS, not yet submitted
    SUBMITTED = "submitted"        # sent to broker
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"          # rejected by risk or broker


class SignalDirection(str, enum.Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class Bar(BaseModel):
    """A single OHLCV bar. Time is the bar's *close* time."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str = "1d"   # 1m, 5m, 1h, 1d, etc.
    adjusted: bool = True  # True if split/dividend-adjusted


class Signal(BaseModel):
    """Model output after aggregation. Strategy turns this into orders."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    ts: datetime
    direction: SignalDirection
    target_weight: float            # Target portfolio weight in [-1, 1]
    confidence: float               # Calibrated probability in [0, 1]
    horizon_bars: int               # How many bars ahead the signal is for
    model_id: str
    model_version: str
    feature_hash: str               # Hash of the feature vector used
    rationale: str = ""             # Human-readable explanation


class Order(BaseModel):
    """An order sitting in the OMS."""

    model_config = ConfigDict(frozen=False)  # status mutates

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_order_id: str = Field(default_factory=lambda: f"sm-{uuid.uuid4().hex[:12]}")
    signal_id: str | None = None
    strategy: str
    symbol: str
    side: OrderSide
    qty: Decimal
    type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    tif: str = "DAY"                # DAY, GTC, IOC, FOK
    created_at: datetime
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: Decimal = Decimal(0)
    avg_fill_price: Decimal | None = None
    reject_reason: str | None = None


class Fill(BaseModel):
    """A single execution against an order. An order may have many fills."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal
    fee: Decimal = Decimal(0)
    venue: str = ""
    ts: datetime


class Position(BaseModel):
    """Aggregate position in a symbol."""

    symbol: str
    qty: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)

    @property
    def is_long(self) -> bool:
        return self.qty > 0

    @property
    def is_short(self) -> bool:
        return self.qty < 0

    @property
    def is_flat(self) -> bool:
        return self.qty == 0
