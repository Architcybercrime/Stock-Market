"""Feature pipeline: assemble a feature matrix from OHLCV bars.

The pipeline is intentionally simple: a list of indicator functions, each
producing one or more columns, concatenated and aligned on the bar index.

Leakage prevention:
- All indicator functions use only past data (see services/features/indicators).
- The label column (constructed by the trainer, not here) is `close.shift(-h)`
  derived; features never see anything indexed after the current bar.
- Output rows where required-window data is missing are *not* dropped here.
  The trainer drops them. This keeps the feature matrix joinable to any label
  horizon without recomputing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd

from services.features import indicators


@dataclass(frozen=True)
class FeatureBundle:
    """A named, versioned set of features. Used by the registry to tie a
    model to the exact features it was trained on."""

    name: str
    version: str
    feature_columns: list[str]
    config: dict = field(default_factory=dict)


# Default bundle for baseline strategies. Production should fork and version this.
DEFAULT_BUNDLE = FeatureBundle(
    name="baseline_v1",
    version="1.0.0",
    feature_columns=[
        "ret_1", "ret_5", "ret_20",
        "logret_1",
        "rv_20",
        "sma_10", "sma_50",
        "ema_12", "ema_26",
        "mom_20",
        "rsi_14",
        "macd", "macd_signal", "macd_hist",
        "bb_pct_b", "bb_bandwidth",
        "atr_14",
        "zscore_close_60",
    ],
    config={"warmup_bars": 60},
)


class FeaturePipeline:
    def __init__(self, bundle: FeatureBundle = DEFAULT_BUNDLE) -> None:
        self.bundle = bundle

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute features for a single symbol's OHLCV DataFrame.

        Input columns required: ts, open, high, low, close, volume.
        Output: input columns + feature columns. Index is preserved.
        """
        if df.empty:
            return df

        close = df["close"]
        out = df.copy()

        # Returns
        out["ret_1"] = indicators.returns(close, 1)
        out["ret_5"] = indicators.returns(close, 5)
        out["ret_20"] = indicators.returns(close, 20)
        out["logret_1"] = indicators.log_returns(close, 1)

        # Volatility
        out["rv_20"] = indicators.realized_volatility(close, 20)

        # Trend
        out["sma_10"] = indicators.sma(close, 10)
        out["sma_50"] = indicators.sma(close, 50)
        out["ema_12"] = indicators.ema(close, 12)
        out["ema_26"] = indicators.ema(close, 26)
        out["mom_20"] = indicators.momentum(close, 20)

        # Oscillators
        out["rsi_14"] = indicators.rsi(close, 14)

        macd_df = indicators.macd(close)
        out[macd_df.columns] = macd_df

        # Bands
        bb_df = indicators.bollinger_bands(close)
        out[["bb_pct_b", "bb_bandwidth"]] = bb_df[["bb_pct_b", "bb_bandwidth"]]

        # ATR (needs OHLC)
        if {"high", "low"}.issubset(out.columns):
            out["atr_14"] = indicators.atr(out, 14)

        # Z-score of close
        out["zscore_close_60"] = indicators.zscore(close, 60)

        return out

    def feature_matrix(self, df: pd.DataFrame, *, dropna: bool = True) -> pd.DataFrame:
        """Return just the feature columns. Optionally drop rows with NaNs."""
        full = self.transform(df)
        cols = ["ts", "symbol"] + [c for c in self.bundle.feature_columns if c in full.columns]
        mat = full[cols]
        if dropna:
            mat = mat.dropna(subset=self.bundle.feature_columns).reset_index(drop=True)
        return mat


def feature_hash(row: pd.Series, columns: list[str]) -> str:
    """Stable hash of a feature vector. Used for audit + reproducibility."""
    payload = ",".join(f"{c}={row[c]:.10g}" for c in columns if c in row.index)
    return hashlib.sha256(payload.encode()).hexdigest()
