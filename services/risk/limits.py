"""Risk limits config — the source of truth.

Defaults match libs.common.config.RiskLimits but this module is what the risk
service imports. Changing limits requires two-person review per RISK_POLICY.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimitsConfig:
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10
    max_position_pct: float = 0.05
    max_sector_pct: float = 0.25
    max_leverage: float = 1.0
    min_cash_buffer_pct: float = 0.05
    max_orders_per_minute: int = 60
    # Hard cap on signal-driven orders per UTC day across all cycles. Bracket
    # exits (stop-loss / take-profit / trailing) are exempt — risk-protective
    # exits must always be allowed through. 0 disables the cap.
    max_orders_per_day: int = 30
    max_order_notional_pct: float = 0.02
    # VaR budget as a fraction of NAV
    max_portfolio_var_pct: float = 0.03
    # Approved symbol whitelist (None = allow all). Production should populate.
    approved_symbols: frozenset[str] | None = None


DEFAULT_LIMITS = RiskLimitsConfig()
