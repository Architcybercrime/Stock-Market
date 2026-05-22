"""Aggregate per-model predictions into a unified Signal.

Each model produces a per-bar prediction (typically expected next-bar log
return) and a confidence in [0, 1]. The aggregator:

1. Filters out predictions whose confidence is below `min_confidence`.
2. Combines remaining predictions via confidence-weighted mean.
3. Translates the combined expected return into a target weight using a
   bounded tanh transform with `weight_scale` controlling aggressiveness.
4. Emits a Signal with direction (long/short/flat), target_weight, and a
   composite confidence (mean of contributing confidences).

Calibration: each model's confidence should be calibrated against its
historical hit rate before being trusted by this aggregator. Use
sklearn.calibration.IsotonicRegression on a hold-out and persist with the
model artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import numpy as np

from libs.common.logging import get_logger
from libs.common.types import Signal, SignalDirection

log = get_logger(__name__)


@dataclass
class ModelPrediction:
    """One model's output for one (symbol, ts)."""

    model_id: str
    model_version: str
    expected_return: float       # e.g., next-bar log return
    confidence: float            # in [0, 1]


class SignalAggregator:
    def __init__(
        self,
        weight_scale: float = 10.0,
        min_confidence: float = 0.55,
        flat_threshold: float = 0.05,
    ) -> None:
        """
        Args:
            weight_scale: target_weight = tanh(weight_scale * combined_expected_return).
                Higher = more aggressive sizing for a given expected return.
            min_confidence: drop predictions with confidence below this.
            flat_threshold: |target_weight| below this becomes FLAT.
        """
        self.weight_scale = weight_scale
        self.min_confidence = min_confidence
        self.flat_threshold = flat_threshold

    def aggregate(
        self,
        symbol: str,
        ts: datetime,
        predictions: Sequence[ModelPrediction],
        horizon_bars: int = 1,
        feature_hash: str = "",
    ) -> Signal | None:
        """Combine predictions for a single (symbol, ts) into a Signal.

        Returns None if no prediction passes the confidence floor.
        """
        usable = [p for p in predictions if p.confidence >= self.min_confidence]
        if not usable:
            log.info(
                "signal.no_usable_predictions",
                symbol=symbol,
                n_total=len(predictions),
                min_confidence=self.min_confidence,
            )
            return None

        weights = np.array([p.confidence for p in usable])
        weights = weights / weights.sum()
        expected = float(np.dot(weights, [p.expected_return for p in usable]))
        combined_conf = float(np.mean([p.confidence for p in usable]))

        target = float(np.tanh(self.weight_scale * expected))
        if abs(target) < self.flat_threshold:
            direction = SignalDirection.FLAT
            target = 0.0
        elif target > 0:
            direction = SignalDirection.LONG
        else:
            direction = SignalDirection.SHORT

        # Aggregate metadata: use the first prediction's model id for the Signal
        # field; the rationale string lists all contributors.
        head = usable[0]
        rationale = "; ".join(
            f"{p.model_id}@{p.model_version}: er={p.expected_return:.4f} c={p.confidence:.2f}"
            for p in usable
        )

        return Signal(
            symbol=symbol,
            ts=ts,
            direction=direction,
            target_weight=target,
            confidence=combined_conf,
            horizon_bars=horizon_bars,
            model_id=f"aggregate:{head.model_id}",
            model_version=head.model_version,
            feature_hash=feature_hash,
            rationale=rationale,
        )
