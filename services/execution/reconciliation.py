"""Periodic reconciliation: catch divergence between local state and broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from libs.common.logging import get_logger
from services.execution.brokers.base import Broker
from services.portfolio.manager import PortfolioManager

log = get_logger(__name__)


@dataclass
class ReconciliationReport:
    positions_diff: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)  # local, broker
    missing_local_orders: list[str] = field(default_factory=list)
    missing_broker_orders: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.positions_diff or self.missing_local_orders or self.missing_broker_orders)


def reconcile(portfolio: PortfolioManager, broker: Broker) -> ReconciliationReport:
    """Compare local portfolio positions against broker positions."""
    report = ReconciliationReport()
    broker_positions = broker.list_positions()

    local_positions = {sym: pos.qty for sym, pos in portfolio.portfolio.positions.items()}

    all_symbols = set(broker_positions) | set(local_positions)
    for sym in all_symbols:
        local_qty = Decimal(local_positions.get(sym, Decimal(0)))
        broker_qty = Decimal(broker_positions.get(sym, Decimal(0)))
        if local_qty != broker_qty:
            report.positions_diff[sym] = (local_qty, broker_qty)

    if not report.ok:
        log.error(
            "reconciliation.divergence",
            positions_diff={k: (str(v[0]), str(v[1])) for k, v in report.positions_diff.items()},
        )
    else:
        log.info("reconciliation.ok")

    return report
