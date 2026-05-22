"""Transaction cost and slippage models.

Defaults are deliberately pessimistic. Better-than-default execution is
*evidence*, not an assumption.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """Commission model in basis points of notional, plus per-trade fixed fee."""

    commission_bps: float = 0.5     # 0.5 bps = 0.005% — better than retail, worse than many institutions
    min_fee: float = 0.0            # Per-trade floor
    sec_fee_bps: float = 0.0022     # SEC + TAF on sells (US equities); applied only to sells

    def fee(self, notional: float, *, is_sell: bool) -> float:
        commission = abs(notional) * self.commission_bps * 1e-4
        sec = abs(notional) * self.sec_fee_bps * 1e-4 if is_sell else 0.0
        return max(commission + sec, self.min_fee)


@dataclass(frozen=True)
class SlippageModel:
    """Slippage applied to the *intended* fill price.

    Two components:
    1. Half-spread: a fixed % of price (proxy for bid-ask).
    2. Market impact: scales with order size as a fraction of average daily volume.

    Result: buys fill at price * (1 + slippage), sells fill at price * (1 - slippage).
    """

    half_spread_bps: float = 1.0       # 1 bp half-spread = 2 bp round-trip on liquid US equities
    impact_coef: float = 0.10          # impact = coef * (qty / adv)
    adv_floor: float = 1.0             # avoid div-by-zero

    def slippage_fraction(self, qty: float, adv: float | None) -> float:
        spread = self.half_spread_bps * 1e-4
        impact = 0.0
        if adv is not None:
            impact = self.impact_coef * abs(qty) / max(adv, self.adv_floor)
        return spread + impact

    def apply(self, intended_price: float, qty: float, adv: float | None, *, is_buy: bool) -> float:
        s = self.slippage_fraction(qty, adv)
        return intended_price * (1.0 + s) if is_buy else intended_price * (1.0 - s)
