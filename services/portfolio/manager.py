"""Portfolio manager.

Tracks cash, positions (with FIFO lots), realized/unrealized P&L, and
provides the PortfolioState snapshots that the risk service consumes.

Long-only is the default. Shorts work but require margin accounting that this
scaffold does not implement; production must add proper margin tracking before
enabling shorts.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from libs.common.logging import get_logger
from libs.common.types import Fill, OrderSide, Position

log = get_logger(__name__)


@dataclass
class _Lot:
    qty: Decimal
    cost: Decimal
    opened_at: datetime


@dataclass
class Portfolio:
    cash: Decimal
    initial_capital: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
    lots: dict[str, deque[_Lot]] = field(default_factory=lambda: defaultdict(deque))
    realized_pnl: Decimal = Decimal(0)
    history: list[tuple[datetime, Decimal]] = field(default_factory=list)

    def equity(self, prices: dict[str, float]) -> Decimal:
        """NAV = cash + sum(qty * mark)."""
        total = self.cash
        for sym, pos in self.positions.items():
            mark = Decimal(str(prices.get(sym, float(pos.avg_cost))))
            total += pos.qty * mark
        return total

    def gross_exposure(self, prices: dict[str, float]) -> Decimal:
        total = Decimal(0)
        for sym, pos in self.positions.items():
            mark = Decimal(str(prices.get(sym, float(pos.avg_cost))))
            total += abs(pos.qty * mark)
        return total

    def positions_notional(self, prices: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for sym, pos in self.positions.items():
            mark = prices.get(sym, float(pos.avg_cost))
            out[sym] = float(pos.qty) * mark
        return out


class PortfolioManager:
    """Owns a Portfolio and processes Fills. Plus a few derived views."""

    def __init__(self, initial_capital: Decimal | float) -> None:
        cap = Decimal(str(initial_capital))
        self.portfolio = Portfolio(cash=cap, initial_capital=cap)

    # ------------------------------------------------------------------ updates

    def apply_fill(self, fill: Fill) -> None:
        """Update cash, positions, and realized P&L from a fill (FIFO)."""
        sym = fill.symbol
        qty = fill.qty
        price = fill.price
        fee = fill.fee
        side = fill.side

        # Cash impact: buy reduces cash, sell adds. Fees always reduce.
        if side == OrderSide.BUY:
            self.portfolio.cash -= qty * price + fee
        else:
            self.portfolio.cash += qty * price - fee

        pos = self.portfolio.positions.get(sym)
        lots = self.portfolio.lots[sym]

        if side == OrderSide.BUY:
            # Adding to long (or covering short — not yet supported beyond simple case)
            if pos and pos.qty < 0:
                # Cover short
                remaining = qty
                while remaining > 0 and lots:
                    lot = lots[0]
                    take = min(remaining, abs(lot.qty))
                    # Short opened at lot.cost, covered at `price` => pnl = (cost - price) * qty
                    realized = (lot.cost - price) * take - (fee * (take / qty))
                    self.portfolio.realized_pnl += realized
                    lot.qty += take  # qty is negative; moving toward zero
                    if lot.qty == 0:
                        lots.popleft()
                    remaining -= take
                if remaining > 0:
                    # Flipped to long; open a new lot for the remainder
                    lots.append(_Lot(qty=remaining, cost=price, opened_at=fill.ts))
            else:
                lots.append(_Lot(qty=qty, cost=price, opened_at=fill.ts))
        else:  # SELL
            if pos and pos.qty > 0:
                # Closing long FIFO
                remaining = qty
                while remaining > 0 and lots:
                    lot = lots[0]
                    take = min(remaining, lot.qty)
                    realized = (price - lot.cost) * take - (fee * (take / qty))
                    self.portfolio.realized_pnl += realized
                    lot.qty -= take
                    if lot.qty == 0:
                        lots.popleft()
                    remaining -= take
                if remaining > 0:
                    # Flipped to short; open a short lot
                    lots.append(_Lot(qty=-remaining, cost=price, opened_at=fill.ts))
            else:
                lots.append(_Lot(qty=-qty, cost=price, opened_at=fill.ts))

        # Rebuild aggregate position from lots
        net_qty = sum((lot.qty for lot in lots), start=Decimal(0))
        if net_qty == 0:
            if sym in self.portfolio.positions:
                del self.portfolio.positions[sym]
            if not lots:
                del self.portfolio.lots[sym]
            return

        total_cost = sum((lot.qty * lot.cost for lot in lots), start=Decimal(0))
        avg = total_cost / net_qty if net_qty != 0 else Decimal(0)
        self.portfolio.positions[sym] = Position(
            symbol=sym, qty=net_qty, avg_cost=avg, realized_pnl=self.portfolio.realized_pnl
        )

    # ------------------------------------------------------------------ views

    def mark_to_market(self, prices: dict[str, float], ts: datetime) -> Decimal:
        """Record equity at this time and return it."""
        eq = self.portfolio.equity(prices)
        self.portfolio.history.append((ts, eq))
        # Update unrealized P&L on each position
        for sym, pos in self.portfolio.positions.items():
            mark = Decimal(str(prices.get(sym, float(pos.avg_cost))))
            self.portfolio.positions[sym] = Position(
                symbol=sym,
                qty=pos.qty,
                avg_cost=pos.avg_cost,
                realized_pnl=pos.realized_pnl,
                unrealized_pnl=(mark - pos.avg_cost) * pos.qty,
            )
        return eq
