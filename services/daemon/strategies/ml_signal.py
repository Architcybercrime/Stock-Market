"""ML-driven signal generator.

Loads a trained model from the registry and turns its next-bar-return
prediction into a [-1, 1] score with calibrated confidence.

This is the most-likely-to-overfit signal in the bunch. Realistic
expectation: useful as a tilt, not as a standalone money-maker.
The aggregator's weighting reflects this.

If no model is registered for a symbol, this generator returns zero
confidence — it does NOT fall back to predicting zero. That keeps the
"no model" case visible in the audit log instead of silently nudging
allocations.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from libs.common.config import settings
from libs.common.logging import get_logger
from services.daemon.strategies.base import SignalGenerator, StrategySignal
from services.features.pipeline import DEFAULT_BUNDLE, FeaturePipeline
from services.ml.registry import ModelRegistry

log = get_logger(__name__)


class MLSignal(SignalGenerator):
    name = "ml"

    def __init__(
        self,
        registry_root: Path | None = None,
        model_id_template: str = "ensemble_{symbol}_1d",
        tanh_scale: float = 50.0,
    ) -> None:
        """
        Args:
            registry_root: where models live on disk.
            model_id_template: format string with {symbol} placeholder. Tried
                first; if not present, also tries "xgboost_{symbol}_1d" and
                "lstm_{symbol}_1d" before giving up.
            tanh_scale: turn an expected log return into a [-1,1] score.
                Default 50 means a +2% predicted move -> score ~0.76.
        """
        self.registry = ModelRegistry(registry_root or Path(settings.data_root) / "registry")
        self.model_id_template = model_id_template
        self.tanh_scale = tanh_scale
        self._feature_pipeline = FeaturePipeline(DEFAULT_BUNDLE)
        self._model_cache: dict[str, object] = {}

    def warmup_bars(self) -> int:
        return 80

    def _load_model(self, symbol: str):
        if symbol in self._model_cache:
            return self._model_cache[symbol]
        candidates = [
            self.model_id_template.format(symbol=symbol),
            f"ensemble_{symbol}_1d",
            f"xgboost_{symbol}_1d",
            f"lstm_{symbol}_1d",
        ]
        for mid in candidates:
            try:
                model = self.registry.load(mid)
                self._model_cache[symbol] = model
                log.info("ml_signal.model_loaded", symbol=symbol, model_id=mid)
                return model
            except (FileNotFoundError, ValueError):
                continue
        self._model_cache[symbol] = None
        return None

    def evaluate(self, symbol: str, history: pd.DataFrame) -> StrategySignal:
        warmup = self.warmup_bars()
        if len(history) < warmup:
            return StrategySignal(
                self.name, symbol, 0.0, 0.0, f"insufficient history ({len(history)}/{warmup})"
            )

        model = self._load_model(symbol)
        if model is None:
            return StrategySignal(self.name, symbol, 0.0, 0.0, "no model registered")

        try:
            features = self._feature_pipeline.transform(history)
            feature_cols = DEFAULT_BUNDLE.feature_columns
            features = features.dropna(subset=feature_cols)
            if features.empty:
                return StrategySignal(self.name, symbol, 0.0, 0.0, "features all-NaN")

            # Take the last available feature row and predict on it.
            x = features[["ts", *feature_cols]].tail(60)
            preds = model.predict(x)
            if len(preds) == 0:
                return StrategySignal(self.name, symbol, 0.0, 0.0, "model returned empty")
            expected_log_return = float(np.asarray(preds)[-1])
        except Exception as exc:
            log.warning("ml_signal.predict_failed", symbol=symbol, error=str(exc))
            return StrategySignal(self.name, symbol, 0.0, 0.0, f"predict_error: {exc}")

        score = float(np.tanh(self.tanh_scale * expected_log_return))

        # Confidence: derived from model metadata's validation r2 if present.
        # If r2 is negative the model is worse than guessing the mean -> zero conf.
        meta = getattr(model, "metadata", None)
        r2 = float(meta.metrics.get("mean_r2", 0.0)) if meta and getattr(meta, "metrics", None) else 0.0
        confidence = max(0.0, min(0.85, 0.5 + r2 * 5.0))  # r2 of 0.07 -> ~0.85

        return StrategySignal(
            strategy=self.name,
            symbol=symbol,
            score=score,
            confidence=confidence,
            rationale=f"E[r]={expected_log_return:+.4f} r2={r2:+.3f}",
        )
