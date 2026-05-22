"""Train a model on a symbol's history with walk-forward validation.

Example:
    python scripts/train_model.py --symbol AAPL --model lstm
    python scripts/train_model.py --symbol AAPL --model xgboost
    python scripts/train_model.py --symbol AAPL --model ensemble
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from services.features.pipeline import DEFAULT_BUNDLE, FeaturePipeline
from services.ingestion.storage import BarStore
from services.ml.models.base import ModelMetadata
from services.ml.models.ensemble import WeightedEnsemble
from services.ml.models.lstm_model import LSTMModel
from services.ml.models.xgboost_model import XGBoostModel
from services.ml.registry import ModelRegistry
from services.ml.training.walk_forward import WalkForwardSplitter, walk_forward_train

log = get_logger("train_model")


def _build_factory(model_kind: str, feature_columns: list[str]):
    if model_kind == "xgboost":
        return lambda: XGBoostModel(feature_columns=feature_columns)
    if model_kind == "lstm":
        return lambda: LSTMModel(feature_columns=feature_columns, max_epochs=10, seq_len=20)
    if model_kind == "ensemble":
        return lambda: WeightedEnsemble(
            models=[
                XGBoostModel(feature_columns=feature_columns),
                LSTMModel(feature_columns=feature_columns, max_epochs=10, seq_len=20),
            ],
        )
    raise ValueError(f"unknown model kind: {model_kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train a model with walk-forward validation")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--model", default="xgboost", choices=["xgboost", "lstm", "ensemble"])
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--label-horizon", type=int, default=1, help="Bars ahead to predict")
    parser.add_argument("--train-years", type=float, default=3.0)
    parser.add_argument("--val-years", type=float, default=1.0)
    parser.add_argument("--step-years", type=float, default=1.0)
    parser.add_argument("--version", default=None, help="Registry version; default = timestamp")
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)

    # 1. Load bars from the local Parquet store.
    store = BarStore(Path(settings.data_root))
    bars = store.read(args.symbol, args.interval)
    if bars.empty:
        log.error("no_data_for_symbol", symbol=args.symbol, interval=args.interval)
        log.error("hint", message="run scripts/ingest_history.py first")
        return 2

    # 2. Compute features.
    pipeline = FeaturePipeline(DEFAULT_BUNDLE)
    features = pipeline.transform(bars)

    # 3. Build the label: log-return `label_horizon` bars ahead.
    features["label"] = np.log(
        features["close"].shift(-args.label_horizon) / features["close"]
    )
    features = features.dropna(subset=DEFAULT_BUNDLE.feature_columns + ["label"]).reset_index(drop=True)
    log.info("training_data_ready", symbol=args.symbol, rows=len(features))

    # 4. Walk-forward train.
    splitter = WalkForwardSplitter(
        train_years=args.train_years,
        val_years=args.val_years,
        step_years=args.step_years,
    )
    factory = _build_factory(args.model, DEFAULT_BUNDLE.feature_columns)

    feature_cols = DEFAULT_BUNDLE.feature_columns
    result = walk_forward_train(
        features_df=features[["ts", "symbol", *feature_cols]],
        label=features["label"],
        feature_columns=feature_cols,
        model_factory=factory,
        splitter=splitter,
    )

    log.info("walk_forward.aggregate", **result["aggregate"])
    if not result["last_model"]:
        log.error("no_folds_produced; not enough history")
        return 3

    # 5. Register the final (most recent) model.
    version = args.version or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    last = result["last_model"]
    # Stamp metadata
    last.metadata = ModelMetadata(
        model_id=f"{args.model}_{args.symbol}_{args.interval}",
        version=version,
        family=last.metadata.family,
        feature_bundle=f"{DEFAULT_BUNDLE.name}@{DEFAULT_BUNDLE.version}",
        trained_at=datetime.now(UTC),
        train_window=(
            pd.to_datetime(result["folds"][-1]["train_window"][0]).to_pydatetime(),
            pd.to_datetime(result["folds"][-1]["train_window"][1]).to_pydatetime(),
        ),
        label_horizon_bars=args.label_horizon,
        label_definition=f"log_return_next_{args.label_horizon}",
        metrics=result["aggregate"],
    )

    registry = ModelRegistry(Path(settings.data_root) / "registry")
    target = registry.register(last, validation_metrics=result["aggregate"])
    log.info("registered", path=str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
