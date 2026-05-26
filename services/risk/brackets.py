"""Protective stop-loss / take-profit checks for open positions.

Runs at the *start* of every daemon cycle, before signal evaluation. Compares
each held position's last price against its avg_cost and the profile's
stop_loss_pct / take_profit_pct thresholds. Returns synthetic SELL orders
for positions that breach a bracket; the daemon submits them through the
normal OMS so risk checks + idempotency still apply.

Why first, not last: if a name is being stopped out, we want to free that
capital before the new-signal sizing step decides where to deploy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BracketExit:
    symbol: str
    qty: float
    reason: str          # e.g. "stop_loss" / "take_profit" / "trailing_stop"
    pnl_pct: float       # signed return from avg_cost at the moment of decision


def check_brackets(
    *,
    positions: dict[str, float],
    avg_costs: dict[str, float],
    last_prices: dict[str, float],
    high_water_marks: dict[str, float] | None = None,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.20,
    trailing_stop_pct: float = 0.0,
) -> list[BracketExit]:
    """Return one exit per position that breached a configured threshold."""
    exits: list[BracketExit] = []
    hwm = high_water_marks or {}

    for sym, qty in positions.items():
        if qty <= 0:
            continue
        avg = avg_costs.get(sym)
        px = last_prices.get(sym)
        if not avg or not px or avg <= 0 or px <= 0:
            continue

        pnl_pct = (px - avg) / avg

        # Hard stop
        if stop_loss_pct > 0 and pnl_pct <= -abs(stop_loss_pct):
            exits.append(BracketExit(sym, qty, "stop_loss", pnl_pct))
            continue

        # Take profit
        if take_profit_pct > 0 and pnl_pct >= abs(take_profit_pct):
            exits.append(BracketExit(sym, qty, "take_profit", pnl_pct))
            continue

        # Trailing stop — only meaningful if we have a high-water mark
        # above the entry. Drop the position if it gives back trailing_stop_pct
        # from its peak.
        if trailing_stop_pct > 0:
            peak = hwm.get(sym, avg)
            if peak > avg and (peak - px) / peak >= abs(trailing_stop_pct):
                exits.append(BracketExit(sym, qty, "trailing_stop", pnl_pct))

    return exits
