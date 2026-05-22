"""Momentum signal generator.

Edge hypothesis: stocks that have outperformed over the last 3-12 months tend
to keep outperforming for the next 1-3 months. This is the single best-
documented anomaly in equity literature (Jegadeesh & Titman 1993 onward).

Implementation: ratio of current price to N-bar trailing price, normalized
to [-1, 1] via tanh. Confidence rises with the magnitude of the move and
falls when volatility is high (a noisy 5% move is less convincing than a
quiet 5% move).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.daemon.strategies.base import SignalGenerator, StrategySignal
from services.features.indicators import realized_volatility


class MomentumSignal(SignalGenerator):
    name = "momentum"

    def __init__(
        self,
        lookback_bars: int = 126,        # ~6 months of daily bars
        skip_bars: int = 21,              # skip the most recent month (reversal effect)
        vol_normalize: bool = True,
        tanh_scale: float = 3.0,
    ) -> None:
        self.lookback_bars = lookback_bars
        self.skip_bars = skip_bars
        self.vol_normalize = vol_normalize
        self.tanh_scale = tanh_scale

    def warmup_bars(self) -> int:
        return self.lookback_bars + self.skip_bars + 20

    def evaluate(self, symbol: str, history: pd.DataFrame) -> StrategySignal:
        n = len(history)
        warmup = self.warmup_bars()
        if n < warmup:
            return StrategySignal(
                strategy=self.name, symbol=symbol, score=0.0, confidence=0.0,
                rationale=f"insufficient history ({n}/{warmup})",
            )

        close = history["close"].astype(float).reset_index(drop=True)
        # 12-1 momentum: ratio of (most-recent-but-skip-last-month) / (lookback-ago)
        cur = close.iloc[-self.skip_bars - 1]
        past = close.iloc[-self.skip_bars - self.lookback_bars - 1]
        if past <= 0 or not np.isfinite(past):
            return StrategySignal(self.name, symbol, 0.0, 0.0, "bad past price")

        raw_return = (cur / past) - 1.0

        # Normalize by volatility so 10% in a calm name and 10% in a chaotic one
        # don't get the same score.
        if self.vol_normalize:
            vol = float(realized_volatility(close, window=63).iloc[-1])
            if not np.isfinite(vol) or vol <= 0:
                vol = 0.20
            risk_adjusted = raw_return / vol
        else:
            risk_adjusted = raw_return

        score = float(np.tanh(self.tanh_scale * risk_adjusted))

        # Confidence: a clear, sustained move scores higher confidence.
        # Look at how monotonic the return path was using % positive months.
        windowed = close.iloc[-self.lookback_bars - self.skip_bars : -self.skip_bars or None]
        monthly = windowed.iloc[::21]
        if len(monthly) >= 3:
            monthly_returns = monthly.pct_change().dropna()
            pos_share = float((monthly_returns > 0).mean())
            # Confidence peaks when ~80% of months were positive (or negative)
            # and the magnitude is non-trivial.
            consistency = abs(pos_share - 0.5) * 2.0  # 0..1
        else:
            consistency = 0.0

        # Magnitude component: bigger moves more convincing, capped.
        magnitude = min(1.0, abs(score))
        confidence = 0.5 + 0.5 * (0.5 * consistency + 0.5 * magnitude)
        confidence = float(min(0.95, max(0.0, confidence)))

        return StrategySignal(
            strategy=self.name,
            symbol=symbol,
            score=score,
            confidence=confidence,
            rationale=(
                f"12-1 ret={raw_return:+.2%} risk_adj={risk_adjusted:+.2f} "
                f"consistency={consistency:.2f}"
            ),
        )
