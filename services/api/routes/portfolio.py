"""Portfolio endpoint: positions, P&L, equity history.

Returns a placeholder PortfolioManager instance until a long-lived process
(paper-trading worker) is wired in. The shape of the response is what the
dashboard expects.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from libs.common.config import settings
from services.api.auth import get_current_user

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PositionView(BaseModel):
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


class PortfolioView(BaseModel):
    nav: Decimal
    cash: Decimal
    initial_capital: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    positions: list[PositionView]


@router.get("/", response_model=PortfolioView)
async def get_portfolio(_user=Depends(get_current_user)) -> PortfolioView:
    """Snapshot of the current portfolio.

    TODO Phase 2: pull live state from a process-resident PortfolioManager
    (or persist to Postgres and read here).
    """
    return PortfolioView(
        nav=Decimal("100000.00"),
        cash=Decimal("100000.00"),
        initial_capital=Decimal("100000.00"),
        realized_pnl=Decimal(0),
        unrealized_pnl=Decimal(0),
        positions=[],
    )
