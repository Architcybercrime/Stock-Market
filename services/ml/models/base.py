"""Model interface used by trainer, ensemble, and inference service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Prediction:
    """Model output for a single bar."""

    point: float          # Point estimate (e.g., expected next-bar log return)
    lower: float | None = None   # Optional lower bound of prediction interval
    upper: float | None = None   # Optional upper bound
    confidence: float | None = None  # In [0, 1] if the model produces it


@dataclass
class ModelMetadata:
    """Frozen metadata captured at training time. Stored alongside weights."""

    model_id: str
    version: str
    family: str           # e.g., "lstm", "xgboost", "ensemble"
    feature_bundle: str   # name@version, e.g. "baseline_v1@1.0.0"
    trained_at: datetime
    train_window: tuple[datetime, datetime]
    label_horizon_bars: int
    label_definition: str       # human-readable, e.g. "log_return_next_5"
    metrics: dict[str, float] = field(default_factory=dict)
    notes: str = ""


class Model(ABC):
    """Common interface for all models.

    Implementations must be deterministic given a seed, must implement save/load
    via files (no shared global state), and must declare their feature_columns
    on the metadata so we can reject mismatched input at inference.
    """

    metadata: ModelMetadata

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Model":
        """Train. Returns self."""

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Point predictions, shape (n,)."""

    def predict_one(self, X: pd.DataFrame) -> Prediction:
        """Convenience: predict a single row and return a Prediction object."""
        if len(X) != 1:
            raise ValueError(f"predict_one expects 1 row, got {len(X)}")
        return Prediction(point=float(self.predict(X)[0]))

    @abstractmethod
    def save(self, path: Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: Path) -> "Model": ...

    def explain(self, X: pd.DataFrame) -> dict[str, Any]:
        """Best-effort explanation (feature importance, SHAP, etc.). Optional."""
        return {}
