"""Per-session risk profile.

The user picks one at daemon start. The profile drives:
- How much of NAV is targeted as invested (the rest stays in cash)
- How many concurrent positions are allowed
- Max single position cap
- Strategy weights (momentum vs mean-rev vs ML)
- Rebalance threshold (how much drift before we trade)

Conservative is the default. Aggressive is *long-only still* — no shorting
in this scaffold. "Aggressive" here means more positions, larger per-name
caps, and higher weight on ML predictions, not leverage or shorts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class RiskProfileName(str, enum.Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    OPPORTUNITY = "opportunity"   # adaptive — opportunity drives trade count + sizing


@dataclass(frozen=True)
class RiskProfile:
    """Knobs the daemon uses to translate signals into orders."""

    name: RiskProfileName

    # Capital deployment
    target_invested_pct: float    # e.g. 0.6 = aim for 60% invested, 40% cash
    max_positions: int             # cap on concurrent open positions
    max_position_pct: float        # cap on any single position as % of NAV
    min_position_pct: float        # below this, we don't bother opening a position

    # Strategy combination weights (must sum to 1.0)
    weight_momentum: float
    weight_mean_reversion: float
    weight_ml: float

    # Action thresholds
    rebalance_threshold_pct: float   # don't trade if delta < this % of NAV
    min_confidence: float            # signals below this are dropped

    # Sizing
    use_volatility_targeting: bool   # scale by inverse volatility
    vol_target_annual: float         # e.g. 0.15 = target 15% annual vol per position

    # Opportunity-adaptive mode: when True, the aggregator scales target_invested_pct
    # by aggregate signal quality. Strong-signal days deploy more capital; weak-signal
    # days deploy less (or nothing). Position count also becomes "up to max_positions"
    # rather than "fill max_positions even with marginal signals".
    opportunity_adaptive: bool = False

    # Per-position protective brackets. Checked at the start of each daemon cycle
    # against the latest close. 0 disables the side.
    #   stop_loss_pct=0.07  → exit if MTM <= -7% from avg_cost
    #   take_profit_pct=0.20 → exit if MTM >= +20% from avg_cost
    # Trailing stop is on the position's high-water mark seen during refresh.
    stop_loss_pct: float = 0.07
    take_profit_pct: float = 0.20
    trailing_stop_pct: float = 0.0   # 0 disables trailing

    description: str = ""

    def validate(self) -> None:
        s = self.weight_momentum + self.weight_mean_reversion + self.weight_ml
        if not (0.99 <= s <= 1.01):
            raise ValueError(f"strategy weights must sum to 1.0, got {s:.3f}")
        if self.max_position_pct <= 0 or self.max_position_pct > 0.5:
            raise ValueError("max_position_pct must be in (0, 0.5]")
        if self.target_invested_pct < 0 or self.target_invested_pct > 1.0:
            raise ValueError("target_invested_pct must be in [0, 1.0]")


PROFILES: dict[RiskProfileName, RiskProfile] = {
    RiskProfileName.CONSERVATIVE: RiskProfile(
        name=RiskProfileName.CONSERVATIVE,
        target_invested_pct=0.60,
        max_positions=5,
        max_position_pct=0.06,
        min_position_pct=0.02,
        weight_momentum=0.50,
        weight_mean_reversion=0.40,
        weight_ml=0.10,
        rebalance_threshold_pct=0.01,
        min_confidence=0.55,
        use_volatility_targeting=True,
        vol_target_annual=0.10,
        description=(
            "Long-only, mostly cash, max 5 positions. Heavy weight on classic "
            "momentum + mean reversion. ML treated as a small tilt. Slow to trade, "
            "small drawdowns. Closest to what works for hands-off systematic "
            "investing."
        ),
    ),
    RiskProfileName.BALANCED: RiskProfile(
        name=RiskProfileName.BALANCED,
        target_invested_pct=0.85,
        max_positions=8,
        max_position_pct=0.08,
        min_position_pct=0.015,
        weight_momentum=0.40,
        weight_mean_reversion=0.30,
        weight_ml=0.30,
        rebalance_threshold_pct=0.008,
        min_confidence=0.50,
        use_volatility_targeting=True,
        vol_target_annual=0.15,
        description=(
            "Long-only, 85% invested target, up to 8 positions. Equal-ish weight "
            "across momentum, mean reversion, and ML. Moderate turnover. Suitable "
            "after you've watched conservative for 60+ days and want more activity."
        ),
    ),
    RiskProfileName.AGGRESSIVE: RiskProfile(
        name=RiskProfileName.AGGRESSIVE,
        target_invested_pct=0.95,
        max_positions=12,
        max_position_pct=0.12,
        min_position_pct=0.01,
        weight_momentum=0.30,
        weight_mean_reversion=0.20,
        weight_ml=0.50,
        rebalance_threshold_pct=0.005,
        min_confidence=0.45,
        use_volatility_targeting=False,   # equal-weight sizing for higher concentration
        vol_target_annual=0.25,
        description=(
            "Long-only but 95% deployed, up to 12 positions, ML-leaning. Higher "
            "drawdowns, more trades, more cost drag. Only run this in paper mode "
            "until you have months of evidence it behaves. The 'aggressive' label "
            "is relative — there is no leverage, no shorting."
        ),
    ),
    RiskProfileName.OPPORTUNITY: RiskProfile(
        name=RiskProfileName.OPPORTUNITY,
        # target_invested_pct here is the CEILING — actual deployment scales down
        # from this based on aggregate signal quality.
        target_invested_pct=0.95,
        max_positions=15,             # ceiling, not target
        max_position_pct=0.08,
        min_position_pct=0.015,
        weight_momentum=0.45,
        weight_mean_reversion=0.35,
        weight_ml=0.20,
        rebalance_threshold_pct=0.008,
        min_confidence=0.50,
        use_volatility_targeting=True,
        vol_target_annual=0.15,
        opportunity_adaptive=True,
        description=(
            "Opportunity-driven. Holds up to 15 positions only if signals warrant. "
            "Deployed capital scales 20-95% with aggregate signal quality. Days "
            "with strong, broad signals will trade 10+ stocks; days with weak or "
            "conflicting signals will sit mostly in cash. Sizes by conviction "
            "(score × confidence) so high-conviction names get larger slices. "
            "This is what the user asked for: 'trade many one day, none the next'."
        ),
    ),
}

for p in PROFILES.values():
    p.validate()


def get_profile(name: str | RiskProfileName) -> RiskProfile:
    if isinstance(name, str):
        name = RiskProfileName(name.lower())
    return PROFILES[name]


def prompt_for_profile(default: RiskProfileName = RiskProfileName.CONSERVATIVE) -> RiskProfile:
    """Interactive prompt. Used by the daemon CLI at start.

    If stdin isn't a TTY (e.g. running under systemd/k8s), returns the default
    so the daemon can still start unattended.
    """
    import sys

    if not sys.stdin.isatty():
        return PROFILES[default]

    print()
    print("=" * 64)
    print(" Pick your risk profile for this session.")
    print(" You can stop the daemon anytime and restart with a different one.")
    print("=" * 64)
    for i, name in enumerate(RiskProfileName, start=1):
        p = PROFILES[name]
        flag = "  (default)" if name == default else ""
        print(f"\n  {i}. {name.value.upper()}{flag}")
        print(f"     - target invested: {p.target_invested_pct:.0%}")
        print(f"     - max positions:   {p.max_positions}")
        print(f"     - max per name:    {p.max_position_pct:.0%}")
        print(f"     - weights: mom={p.weight_momentum:.2f} "
              f"mr={p.weight_mean_reversion:.2f} ml={p.weight_ml:.2f}")
        print(f"     {p.description}")
    print()
    while True:
        choice = input(f"Choose 1, 2, or 3 [default={default.value}]: ").strip()
        if not choice:
            return PROFILES[default]
        try:
            idx = int(choice)
            return PROFILES[list(RiskProfileName)[idx - 1]]
        except (ValueError, IndexError):
            print("Invalid choice. Try again.")
