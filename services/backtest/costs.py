"""Transaction cost and slippage models.

Defaults are deliberately pessimistic. Better-than-default execution is
*evidence*, not an assumption.

Two cost models ship:
- CostModel: US equity defaults (Alpaca-style commission-free + SEC/TAF)
- IndianEquityCostModel: NSE/BSE retail discount broker defaults
  (Zerodha-style ₹20 cap + STT + stamp + exchange charges + GST)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """US equity costs. Commission in basis points of notional + fixed floor."""

    commission_bps: float = 0.5     # 0.5 bps = 0.005% — better than retail, worse than many institutions
    min_fee: float = 0.0            # Per-trade floor
    sec_fee_bps: float = 0.0022     # SEC + TAF on sells (US equities); applied only to sells

    def fee(self, notional: float, *, is_sell: bool) -> float:
        commission = abs(notional) * self.commission_bps * 1e-4
        sec = abs(notional) * self.sec_fee_bps * 1e-4 if is_sell else 0.0
        return max(commission + sec, self.min_fee)


@dataclass(frozen=True)
class IndianEquityCostModel:
    """NSE/BSE retail costs. Matches Zerodha/Upstox-style equity delivery pricing.

    For DELIVERY (CNC) trades — the daily-close trading we do:
    - Brokerage:        0.03% or ₹20, whichever is LOWER (often actually ₹0 for delivery
                        at Zerodha, but we keep a small charge for safety)
    - STT on sell:      0.1% of sell notional
    - Stamp on buy:     0.015% of buy notional (capped at ₹1500/day, ignored here)
    - Exchange (NSE):   0.00322% of notional
    - SEBI:             0.0001% of notional
    - GST (on broker+exchange charges): 18%

    Total ends up roughly:
      Buy side:  ~0.04%  (brokerage + GST + stamp + exchange + SEBI)
      Sell side: ~0.14%  (above + STT)
      Round-trip: ~0.18% of notional

    These match Zerodha's brokerage calculator within a few bps. For paper
    trading + early-stage live, this is a sensible pessimistic default.
    """

    brokerage_pct: float = 0.0003          # 0.03%
    brokerage_cap_rupees: float = 20.0     # per-trade cap
    stt_pct_on_sell: float = 0.001         # 0.1% on sell notional (delivery)
    stamp_pct_on_buy: float = 0.00015      # 0.015% on buy notional
    exchange_pct: float = 0.0000322        # NSE
    sebi_pct: float = 0.000001             # 0.0001%
    gst_pct: float = 0.18                  # on (brokerage + exchange)

    def fee(self, notional: float, *, is_sell: bool) -> float:
        notional = abs(notional)
        brokerage = min(notional * self.brokerage_pct, self.brokerage_cap_rupees)
        exchange = notional * self.exchange_pct
        sebi = notional * self.sebi_pct
        gst = (brokerage + exchange) * self.gst_pct

        if is_sell:
            stt = notional * self.stt_pct_on_sell
            stamp = 0.0
        else:
            stt = 0.0
            stamp = notional * self.stamp_pct_on_buy

        return brokerage + stt + stamp + exchange + sebi + gst


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
