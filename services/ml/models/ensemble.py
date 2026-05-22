"""Weighted ensemble of base models."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from services.ml.models.base import Model, ModelMetadata


class WeightedEnsemble(Model):
    """Convex combination of base models.

    Weights are normalized to sum to 1. If `auto_weight=True`, weights are
    derived from each model's recent out-of-sample R^2 (negative R^2 floored
    at zero) — this gives the trainer a hook to recalibrate without touching
    the ensemble logic.
    """

    family: str = "ensemble"

    def __init__(
        self,
        models: list[Model],
        weights: list[float] | None = None,
        metadata: ModelMetadata | None = None,
    ) -> None:
        if not models:
            raise ValueError("ensemble needs at least one model")
        self.models = models
        if weights is None:
            weights = [1.0 / len(models)] * len(models)
        self.weights = self._normalize_weights(weights)
        # Inherit feature columns from the first model; all members must agree.
        cols = models[0].feature_columns  # type: ignore[attr-defined]
        for m in models[1:]:
            if list(getattr(m, "feature_columns", [])) != list(cols):
                raise ValueError("ensemble members must share feature_columns")
        self.feature_columns = list(cols)
        self.metadata = metadata or ModelMetadata(
            model_id="ensemble",
            version="dev",
            family=self.family,
            feature_bundle=models[0].metadata.feature_bundle,
            trained_at=datetime.now(UTC),
            train_window=models[0].metadata.train_window,
            label_horizon_bars=models[0].metadata.label_horizon_bars,
            label_definition=models[0].metadata.label_definition,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "WeightedEnsemble":
        for m in self.models:
            m.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        preds = []
        for m, w in zip(self.models, self.weights, strict=True):
            p = m.predict(X)
            # If models predict on differently-lengthed sequence outputs (LSTM
            # skips the first seq_len-1), align to the shortest.
            preds.append((p, w))
        min_len = min(len(p) for p, _ in preds)
        stacked = np.stack([p[-min_len:] for p, _ in preds])
        w = np.array([w for _, w in preds]).reshape(-1, 1)
        return (stacked * w).sum(axis=0)

    def recalibrate(self, X_val: pd.DataFrame, y_val: pd.Series) -> None:
        """Reweight by out-of-sample R^2 on (X_val, y_val)."""
        scores = []
        for m in self.models:
            preds = m.predict(X_val)
            if len(preds) == 0:
                scores.append(0.0)
                continue
            y_aligned = y_val.to_numpy()[-len(preds):]
            ss_res = float(np.sum((y_aligned - preds) ** 2))
            ss_tot = float(np.sum((y_aligned - y_aligned.mean()) ** 2)) + 1e-12
            r2 = 1.0 - ss_res / ss_tot
            scores.append(max(0.0, r2))
        if sum(scores) == 0:
            scores = [1.0] * len(self.models)
        self.weights = self._normalize_weights(scores)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        for i, m in enumerate(self.models):
            m.save(path / f"member_{i}_{m.family}")
        (path / "ensemble.json").write_text(
            json.dumps(
                {
                    "members": [
                        {"family": m.family, "dir": f"member_{i}_{m.family}"}
                        for i, m in enumerate(self.models)
                    ],
                    "weights": self.weights,
                    "feature_columns": self.feature_columns,
                    "metadata": {
                        **self.metadata.__dict__,
                        "trained_at": self.metadata.trained_at.isoformat(),
                        "train_window": [t.isoformat() for t in self.metadata.train_window],
                    },
                },
                indent=2,
                default=str,
            )
        )

    @classmethod
    def load(cls, path: Path) -> "WeightedEnsemble":
        from services.ml.models.lstm_model import LSTMModel
        from services.ml.models.xgboost_model import XGBoostModel

        path = Path(path)
        manifest = json.loads((path / "ensemble.json").read_text())
        loaders: dict[str, type[Model]] = {"lstm": LSTMModel, "xgboost": XGBoostModel}
        members = [loaders[m["family"]].load(path / m["dir"]) for m in manifest["members"]]
        m = manifest["metadata"]
        metadata = ModelMetadata(
            model_id=m["model_id"],
            version=m["version"],
            family=m["family"],
            feature_bundle=m["feature_bundle"],
            trained_at=datetime.fromisoformat(m["trained_at"]),
            train_window=(
                datetime.fromisoformat(m["train_window"][0]),
                datetime.fromisoformat(m["train_window"][1]),
            ),
            label_horizon_bars=m["label_horizon_bars"],
            label_definition=m["label_definition"],
            metrics=m.get("metrics", {}),
            notes=m.get("notes", ""),
        )
        return cls(models=members, weights=manifest["weights"], metadata=metadata)

    @staticmethod
    def _normalize_weights(weights: list[float]) -> list[float]:
        total = sum(weights)
        if total <= 0:
            return [1.0 / len(weights)] * len(weights)
        return [w / total for w in weights]
