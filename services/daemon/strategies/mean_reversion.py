"""Mean reversion signal generator.

Edge hypothesis: short-term overreactions revert. When a stock falls
sharply on no fundamental news, buyers step in over the following days.

Implementation: rolling z-score of close vs short-window mean, with the
sign inverted (very negative price deviation -> strong buy signal).
Penalizes by long-term trend so we don't catch falling knives in
structural downtrends.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.daemon.strategies.base import SignalGenerator, StrategySignal


class MeanReversionSignal(SignalGenerator):
    name = "mean_reversion"

    def __init__(
        self,
        zscore_window: int = 10,
        trend_window: int = 200,
        max_abs_z: float = 4.0,
    ) -> None:
        self.zscore_window = zscore_window
        self.trend_window = trend_window
        self.max_abs_z = max_abs_z

    def warmup_bars(self) -> int:
        return self.trend_window + 5

    def evaluate(self, symbol: str, history: pd.DataFrame) -> StrategySignal:
        n = len(history)
        warmup = self.warmup_bars()
        if n < warmup:
            return StrategySignal(
                strategy=self.name, symbol=symbol, score=0.0, confidence=0.0,
                rationale=f"insufficient history ({n}/{warmup})",
            )

        close = history["close"].astype(float).reset_index(drop=True)
        # Short-window z-score
        recent = close.iloc[-self.zscore_window:]
        mu = recent.mean()
        sigma = recent.std()
        if sigma == 0 or not np.isfinite(sigma):
            return StrategySignal(self.name, symbol, 0.0, 0.0, "zero short-window vol")
        z = (close.iloc[-1] - mu) / sigma

        # Long-term trend filter — only mean-revert *with* the trend, not against it.
        # If 200-bar SMA is rising, we trust dips (negative z -> buy).
        # If 200-bar SMA is falling, we ignore the signal (avoid falling knives).
        sma_long = close.iloc[-self.trend_window:].mean()
        prior_sma_long = close.iloc[-self.trend_window - 10 : -10].mean() if n >= self.trend_window + 10 else sma_long
        trend_up = sma_long > prior_sma_long

        # Score: negative z while trend_up -> positive buy score.
        # Clip z to avoid scoring on outliers (those are usually structural breaks).
        z = float(max(-self.max_abs_z, min(self.max_abs_z, z)))
        raw_signal = -z / self.max_abs_z if trend_up else 0.0
        score = float(np.tanh(2.0 * raw_signal))

        # Confidence: higher when z is between -1.5 and -2.5 (sweet spot for reversion)
        # Beyond -3 is usually structural; below -1 is noise.
        z_abs = abs(z)
        if not trend_up:
            confidence = 0.20
        elif 1.5 <= z_abs <= 2.5:
            confidence = 0.70
        elif 1.0 <= z_abs < 1.5 or 2.5 < z_abs <= 3.0:
            confidence = 0.55
        else:
            confidence = 0.35

        return StrategySignal(
            strategy=self.name,
            symbol=symbol,
            score=score,
            confidence=confidence,
            rationale=f"z={z:+.2f} trend_up={trend_up}",
        )
