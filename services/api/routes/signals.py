"""Signals endpoint.

In Phase 1 (this scaffold) the route returns a stubbed list. Phase 2 wires it
to the signal aggregator running against live data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from libs.common.types import Signal, SignalDirection
from services.api.auth import get_current_user

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/", response_model=list[Signal])
async def list_signals(
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> list[Signal]:
    """Return the most recent signals, optionally filtered by symbol.

    TODO Phase 2: read from the signals table or the in-memory aggregator.
    """
    # Stubbed sample to make the route inspectable from the dashboard.
    sample = Signal(
        symbol=symbol or "AAPL",
        ts=datetime.now(UTC),
        direction=SignalDirection.FLAT,
        target_weight=0.0,
        confidence=0.5,
        horizon_bars=1,
        model_id="stub",
        model_version="0.0.0",
        feature_hash="",
        rationale="placeholder until aggregator is wired",
    )
    return [sample]
