"""Combine per-strategy signals into target portfolio weights, then orders.

Pipeline:
1. For each (symbol, strategy) get a StrategySignal.
2. Compute the symbol-level combined score = profile-weighted average of
   per-strategy scores, where each strategy's vote is itself weighted by
   its confidence.
3. Filter out symbols with combined confidence below profile.min_confidence.
4. Clamp scores to [0, 1] for long-only operation. (Negative scores become
   exits if the position is currently held, otherwise ignored.)
5. Rank by combined score, pick the top-N where N = profile.max_positions.
6. Compute target weights from scores, normalized to sum to
   profile.target_invested_pct of NAV.
7. Apply per-position cap (profile.max_position_pct).
8. Apply volatility targeting if enabled.
9. Compare to current holdings and produce buy/sell orders for the deltas
   that exceed profile.rebalance_threshold_pct.

The output is a list of TargetOrder objects (same shape as the backtester
uses) that the daemon hands to the OMS one by one.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from libs.common.logging import get_logger
from libs.common.types import OrderSide
from services.backtest.engine import TargetOrder
from services.daemon.profiles import RiskProfile
from services.daemon.strategies.base import StrategySignal
from services.features.indicators import realized_volatility

log = get_logger(__name__)


@dataclass
class CombinedSignal:
    """Symbol-level decision after aggregating strategies."""

    symbol: str
    score: float
    confidence: float
    target_weight: float
    contributors: list[StrategySignal]

    @property
    def rationale(self) -> str:
        parts = [
            f"{s.strategy}: score={s.score:+.2f} conf={s.confidence:.2f}"
            for s in self.contributors
        ]
        return " | ".join(parts)


def _combine_symbol_signals(
    symbol: str,
    signals: list[StrategySignal],
    profile: RiskProfile,
) -> CombinedSignal:
    """Confidence-weighted combination of per-strategy signals for one symbol.

    "No opinion" signals (confidence == 0, e.g. ML signal when no model is
    registered) are EXCLUDED from the combined confidence — otherwise they
    artificially drag down the average and filter out strong opinions from
    the other strategies. They still don't contribute to the weighted score
    because their effective_w is also zero, so this is the right semantics:
    "no opinion" = "doesn't vote at all", not "votes zero".
    """
    weight_map = {
        "momentum": profile.weight_momentum,
        "mean_reversion": profile.weight_mean_reversion,
        "ml": profile.weight_ml,
    }
    total_w = 0.0
    weighted_score = 0.0
    opinion_confidences: list[float] = []
    for s in signals:
        strat_w = weight_map.get(s.strategy, 0.0)
        effective_w = strat_w * s.confidence
        weighted_score += effective_w * s.score
        total_w += effective_w
        if s.confidence > 0:
            opinion_confidences.append(s.confidence)

    if total_w == 0 or not opinion_confidences:
        score = 0.0
        confidence = 0.0
    else:
        score = weighted_score / total_w
        confidence = float(np.mean(opinion_confidences))

    return CombinedSignal(
        symbol=symbol,
        score=score,
        confidence=confidence,
        target_weight=0.0,  # filled below
        contributors=signals,
    )


def _volatility_target_weight(price_history: pd.DataFrame, vol_target_annual: float) -> float:
    """Return the position weight multiplier so this position contributes
    `vol_target_annual` annualized volatility on its own.

    Output is in (0, 5] — clamped to avoid sizing a calm stock to absurd
    weights when sigma is microscopic.
    """
    rv = realized_volatility(price_history["close"].astype(float), window=63)
    sigma = float(rv.iloc[-1]) if not rv.empty else 0.20
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = 0.20
    multiplier = vol_target_annual / sigma
    return max(0.05, min(5.0, multiplier))


@dataclass
class AggregatorResult:
    combined: list[CombinedSignal]                # all symbols, ranked
    selected: list[CombinedSignal]                 # subset that meets the cut
    target_weights: dict[str, float]              # symbol -> target weight in [0,1]
    orders: list[TargetOrder]                     # delta orders to reach target
    cash_target: float                            # target cash as fraction of NAV
    nav: float
    current_weights: dict[str, float]


class SignalAggregator:
    """Stateless — takes today's signals + portfolio, returns orders."""

    def __init__(self, profile: RiskProfile) -> None:
        profile.validate()
        self.profile = profile

    def aggregate(
        self,
        signals_by_symbol: dict[str, list[StrategySignal]],
        price_history: dict[str, pd.DataFrame],
        current_positions: dict[str, float],   # symbol -> qty
        last_prices: dict[str, float],          # symbol -> latest close
        nav: float,
    ) -> AggregatorResult:
        p = self.profile

        # 1. Combine per-symbol.
        combined: list[CombinedSignal] = [
            _combine_symbol_signals(sym, sigs, p)
            for sym, sigs in signals_by_symbol.items()
        ]

        # 2. Filter and clamp.
        kept = [
            c for c in combined
            if c.confidence >= p.min_confidence and c.score > 0
        ]

        # 3. Rank, pick top-N.
        kept.sort(key=lambda c: c.score * c.confidence, reverse=True)
        selected = kept[: p.max_positions]

        # 4. Score-weighted target allocation.
        if selected:
            score_total = sum(c.score for c in selected) or 1.0
            base_weights: dict[str, float] = {
                c.symbol: (c.score / score_total) * p.target_invested_pct
                for c in selected
            }
        else:
            base_weights = {}

        # 5. Volatility scaling (optional).
        if p.use_volatility_targeting:
            multipliers: dict[str, float] = {}
            for sym in base_weights:
                hist = price_history.get(sym)
                if hist is None or len(hist) < 63:
                    multipliers[sym] = 1.0
                else:
                    multipliers[sym] = _volatility_target_weight(hist, p.vol_target_annual)
            # Re-normalize after scaling
            scaled = {sym: base_weights[sym] * multipliers[sym] for sym in base_weights}
            total_scaled = sum(scaled.values()) or 1.0
            scale_back = p.target_invested_pct / total_scaled
            base_weights = {sym: w * scale_back for sym, w in scaled.items()}

        # 6. Cap per position.
        capped_weights: dict[str, float] = {
            sym: min(p.max_position_pct, w) for sym, w in base_weights.items()
        }
        # Drop below min_position_pct
        capped_weights = {
            sym: w for sym, w in capped_weights.items() if w >= p.min_position_pct
        }

        # Re-normalize (caps may have freed up budget; min cut may have freed more)
        total = sum(capped_weights.values())
        if total > p.target_invested_pct and total > 0:
            scale = p.target_invested_pct / total
            capped_weights = {sym: w * scale for sym, w in capped_weights.items()}

        # 7. Current weights (for display + delta computation).
        current_weights: dict[str, float] = {}
        for sym, qty in current_positions.items():
            px = last_prices.get(sym)
            if px is None:
                continue
            current_weights[sym] = float(qty) * px / nav if nav > 0 else 0.0

        # 8. Delta orders — both buys (to reach target) and sells (to exit dropped).
        orders: list[TargetOrder] = []
        all_symbols = set(capped_weights) | set(current_positions)
        for sym in all_symbols:
            target_w = capped_weights.get(sym, 0.0)
            current_w = current_weights.get(sym, 0.0)
            delta_w = target_w - current_w
            if abs(delta_w) < p.rebalance_threshold_pct:
                continue
            px = last_prices.get(sym)
            if px is None or px <= 0:
                log.warning("aggregator.missing_price", symbol=sym)
                continue
            qty_delta = abs(delta_w) * nav / px
            # Round to whole shares (fractional shares possible on Alpaca but
            # default to whole for cleaner attribution; revisit later).
            qty = round(qty_delta)
            if qty <= 0:
                continue
            side = "buy" if delta_w > 0 else "sell"
            # Don't try to sell more than we hold
            if side == "sell":
                qty = min(qty, int(abs(float(current_positions.get(sym, 0)))))
                if qty == 0:
                    continue
            orders.append(TargetOrder(symbol=sym, side=side, qty=float(qty)))

        cash_target = max(0.0, 1.0 - sum(capped_weights.values()))
        return AggregatorResult(
            combined=combined,
            selected=selected,
            target_weights=capped_weights,
            orders=orders,
            cash_target=cash_target,
            nav=nav,
            current_weights=current_weights,
        )
