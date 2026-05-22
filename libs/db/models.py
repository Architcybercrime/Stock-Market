"""SQLAlchemy models. Mirror, do not replace, the domain types in libs.common.

Domain types (libs.common.types) are what services pass around at runtime;
these models are how that state is persisted. Conversion happens at the edges.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BarModel(Base):
    __tablename__ = "bars"
    __table_args__ = (
        UniqueConstraint("symbol", "ts", "interval", name="uq_bar_symbol_ts_interval"),
        Index("ix_bars_symbol_ts", "symbol", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignalModel(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_symbol_ts", "symbol", "ts"),
        Index("ix_signals_model", "model_id", "model_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    target_weight: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    horizon_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="")


class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_symbol_status", "symbol", "status"),
        Index("ix_orders_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    signal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("signals.id"))
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="market")
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    tif: Mapped[str] = mapped_column(String(8), default="DAY")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal(0))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    fills: Mapped[list[FillModel]] = relationship(back_populates="order")


class FillModel(Base):
    __tablename__ = "fills"
    __table_args__ = (Index("ix_fills_order_id", "order_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal(0))
    venue: Mapped[str] = mapped_column(String(32), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped[OrderModel] = relationship(back_populates="fills")


class AuditLog(Base):
    """Append-only audit trail with hash-chain integrity.

    Each row stores the SHA-256 of the previous row's `payload`. Tampering with
    an old row breaks the chain. `verify_chain()` walks the table to confirm.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_ts", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)  # service or user
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    row_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
