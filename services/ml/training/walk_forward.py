"""Walk-forward training and validation.

Why walk-forward and not k-fold:
- Random splits leak future into the past.
- A single hold-out test can be lucky.
- Walk-forward tests how the model would have performed if deployed at
  successive points in time, which is what we actually care about.

Default config: 5-year train window, 1-year validation, 1-year roll step.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from libs.common.logging import get_logger
from services.ml.models.base import Model

log = get_logger(__name__)


@dataclass
class WalkForwardSplitter:
    """Yields (train_idx, val_idx) for time-ordered DataFrames."""

    train_years: float = 5.0
    val_years: float = 1.0
    step_years: float = 1.0
    min_train_rows: int = 252

    def split(self, ts: pd.Series) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """`ts` must be sorted ascending and timezone-aware."""
        if len(ts) < self.min_train_rows:
            return

        start = ts.iloc[0]
        end = ts.iloc[-1]
        train_delta = timedelta(days=int(365 * self.train_years))
        val_delta = timedelta(days=int(365 * self.val_years))
        step_delta = timedelta(days=int(365 * self.step_years))

        cursor = start + train_delta
        while cursor + val_delta <= end + timedelta(days=1):
            train_end: datetime = cursor
            val_end: datetime = cursor + val_delta

            train_mask = ts < train_end
            val_mask = (ts >= train_end) & (ts < val_end)

            train_idx = np.where(train_mask)[0]
            val_idx = np.where(val_mask)[0]

            if len(train_idx) < self.min_train_rows or len(val_idx) == 0:
                cursor += step_delta
                continue

            yield train_idx, val_idx
            cursor += step_delta


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    if len(y_true) == 0 or len(y_pred) == 0:
        return {}
    n = min(len(y_true), len(y_pred))
    y_true = y_true[-n:]
    y_pred = y_pred[-n:]
    mse = float(np.mean((y_true - y_pred) ** 2))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2)) + 1e-12
    r2 = 1.0 - ss_res / ss_tot
    # Directional accuracy (sign of return)
    dir_acc = float(np.mean(np.sign(y_true) == np.sign(y_pred)))
    # Information coefficient = Spearman correlation between pred and actual
    ic = float(pd.Series(y_pred).corr(pd.Series(y_true), method="spearman"))
    return {"mse": mse, "mae": mae, "r2": r2, "directional_acc": dir_acc, "ic_spearman": ic}


def walk_forward_train(
    features_df: pd.DataFrame,
    label: pd.Series,
    feature_columns: list[str],
    model_factory: Callable[[], Model],
    splitter: WalkForwardSplitter | None = None,
) -> dict:
    """Run walk-forward training and return aggregate + per-fold metrics.

    Returns:
        {
            "folds": [{"train_window": ..., "val_window": ..., "metrics": {...}}, ...],
            "aggregate": {"mean_r2": ..., "mean_dir_acc": ..., ...},
            "last_model": Model  # the model trained on the most recent train window
        }

    The trainer returns the *most recently* trained model. Earlier folds are
    used for validation only; we do not retain those models.
    """
    splitter = splitter or WalkForwardSplitter()
    df = features_df.copy().reset_index(drop=True)
    y = label.reset_index(drop=True)

    if "ts" not in df.columns:
        raise ValueError("features_df must have a 'ts' column")
    ts = pd.to_datetime(df["ts"], utc=True)
    if not ts.is_monotonic_increasing:
        order = ts.argsort()
        df = df.iloc[order].reset_index(drop=True)
        y = y.iloc[order].reset_index(drop=True)
        ts = ts.iloc[order].reset_index(drop=True)

    folds: list[dict] = []
    last_model: Model | None = None

    for fold_i, (train_idx, val_idx) in enumerate(splitter.split(ts)):
        X_train = df.iloc[train_idx]
        y_train = y.iloc[train_idx]
        X_val = df.iloc[val_idx]
        y_val = y.iloc[val_idx]

        model = model_factory()
        model.fit(X_train[feature_columns + ["ts"]], y_train)
        preds = model.predict(X_val[feature_columns + ["ts"]])
        m = _metrics(y_val.to_numpy(), np.asarray(preds))

        fold = {
            "fold": fold_i,
            "train_window": (ts.iloc[train_idx[0]].isoformat(), ts.iloc[train_idx[-1]].isoformat()),
            "val_window": (ts.iloc[val_idx[0]].isoformat(), ts.iloc[val_idx[-1]].isoformat()),
            "n_train": int(len(train_idx)),
            "n_val": int(len(val_idx)),
            "metrics": m,
        }
        folds.append(fold)
        last_model = model
        log.info(
            "walk_forward.fold",
            fold=fold_i,
            n_train=len(train_idx),
            n_val=len(val_idx),
            **m,
        )

    if not folds:
        log.warning("walk_forward.no_folds_produced")
        return {"folds": [], "aggregate": {}, "last_model": None}

    agg: dict[str, float] = {}
    metric_keys = set().union(*(f["metrics"].keys() for f in folds))
    for k in metric_keys:
        vals = [f["metrics"][k] for f in folds if k in f["metrics"] and not np.isnan(f["metrics"][k])]
        if vals:
            agg[f"mean_{k}"] = float(np.mean(vals))
            agg[f"std_{k}"] = float(np.std(vals))

    return {"folds": folds, "aggregate": agg, "last_model": last_model}
