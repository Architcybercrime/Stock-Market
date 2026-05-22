"""XGBoost regressor on engineered features."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.ml.models.base import Model, ModelMetadata


class XGBoostModel(Model):
    """Wraps XGBRegressor with our Model interface.

    Default objective is squared error on next-bar log returns. Override the
    objective if you want classification (up/down) or quantile regression.
    """

    family: str = "xgboost"

    def __init__(
        self,
        feature_columns: list[str],
        params: dict[str, Any] | None = None,
        metadata: ModelMetadata | None = None,
    ) -> None:
        from xgboost import XGBRegressor

        defaults: dict[str, Any] = {
            "n_estimators": 500,
            "max_depth": 5,
            "learning_rate": 0.03,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_lambda": 1.0,
            "objective": "reg:squarederror",
            "tree_method": "hist",
            "random_state": 42,
            "n_jobs": -1,
        }
        if params:
            defaults.update(params)
        self.params = defaults
        self.feature_columns = list(feature_columns)
        self.model = XGBRegressor(**self.params)
        self.metadata = metadata or ModelMetadata(
            model_id="xgboost",
            version="dev",
            family=self.family,
            feature_bundle="baseline_v1@1.0.0",
            trained_at=datetime.now(UTC),
            train_window=(datetime.now(UTC), datetime.now(UTC)),
            label_horizon_bars=1,
            label_definition="log_return_next_1",
        )

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "XGBoostModel":
        self._check_columns(X)
        self.model.fit(X[self.feature_columns], y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._check_columns(X)
        return self.model.predict(X[self.feature_columns])

    def explain(self, X: pd.DataFrame) -> dict[str, Any]:
        importances = self.model.feature_importances_
        return {col: float(imp) for col, imp in zip(self.feature_columns, importances, strict=False)}

    def save(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.model.save_model(path / "model.json")
        meta = {
            "feature_columns": self.feature_columns,
            "params": self.params,
            "metadata": {
                **self.metadata.__dict__,
                "trained_at": self.metadata.trained_at.isoformat(),
                "train_window": [t.isoformat() for t in self.metadata.train_window],
            },
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "XGBoostModel":
        from xgboost import XGBRegressor

        path = Path(path)
        meta = json.loads((path / "meta.json").read_text())
        m = meta["metadata"]
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
        obj = cls(feature_columns=meta["feature_columns"], params=meta["params"], metadata=metadata)
        obj.model = XGBRegressor(**meta["params"])
        obj.model.load_model(path / "model.json")
        return obj

    def _check_columns(self, X: pd.DataFrame) -> None:
        missing = set(self.feature_columns) - set(X.columns)
        if missing:
            raise ValueError(f"missing feature columns: {sorted(missing)}")
