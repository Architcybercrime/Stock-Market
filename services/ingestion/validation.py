"""Validate and clean ingested bars.

Validation is *strict by default*: any anomaly raises. The pipeline can choose
to drop bad rows instead, but it must do so explicitly so we never silently
ingest garbage into the feature pipeline.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from libs.common.logging import get_logger

log = get_logger(__name__)


class BarValidationError(ValueError):
    """Raised when a bar fails validation and the caller asked for strict mode."""


def validate_bars(df: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    """Return a validated, sorted DataFrame.

    Checks:
    - Required columns present
    - No non-finite OHLC
    - low <= min(open, close) and high >= max(open, close)
    - volume >= 0
    - No duplicate (symbol, ts) pairs
    - Timestamps are timezone-aware

    In strict mode, the first failure raises. Otherwise bad rows are dropped
    and a structured warning is logged.
    """
    required = {"ts", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise BarValidationError(f"missing columns: {sorted(missing)}")

    if df.empty:
        return df

    # Timezone check
    if not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df = df.copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    # Coerce naive to UTC to be safe
    if df["ts"].dt.tz is None:
        df = df.copy()
        df["ts"] = df["ts"].dt.tz_localize("UTC")

    issues: list[str] = []

    # Non-finite
    ohlc = df[["open", "high", "low", "close"]]
    bad_finite = ~np.isfinite(ohlc.to_numpy()).all(axis=1)
    if bad_finite.any():
        issues.append(f"{int(bad_finite.sum())} rows with non-finite OHLC")

    # Range sanity: low <= min(o,c) and high >= max(o,c)
    bad_range = (df["low"] > df[["open", "close"]].min(axis=1)) | (
        df["high"] < df[["open", "close"]].max(axis=1)
    )
    if bad_range.any():
        issues.append(f"{int(bad_range.sum())} rows with inverted high/low vs open/close")

    # Non-positive close
    bad_price = df["close"] <= 0
    if bad_price.any():
        issues.append(f"{int(bad_price.sum())} rows with non-positive close")

    # Negative volume
    bad_vol = df["volume"] < 0
    if bad_vol.any():
        issues.append(f"{int(bad_vol.sum())} rows with negative volume")

    # Duplicates
    dup_mask = df.duplicated(subset=["symbol", "ts"], keep="first")
    if dup_mask.any():
        issues.append(f"{int(dup_mask.sum())} duplicate (symbol, ts) rows")

    bad_any = bad_finite | bad_range | bad_price | bad_vol | dup_mask

    if issues:
        log.warning("validate_bars.issues", issues=issues, symbol=df["symbol"].iloc[0] if len(df) else None)
        if strict:
            raise BarValidationError("; ".join(issues))
        df = df.loc[~bad_any].copy()

    df = df.sort_values(["symbol", "ts"]).reset_index(drop=True)
    return df


def report_gaps(df: pd.DataFrame, *, interval: str = "1d") -> pd.DataFrame:
    """Report missing-bar gaps for visibility.

    Returns a DataFrame of (symbol, gap_start, gap_end, missing_bars). This is
    informational; the pipeline does not auto-fill. Forward-filling prices
    silently corrupts returns and is never done here.
    """
    if df.empty:
        return pd.DataFrame(columns=["symbol", "gap_start", "gap_end", "missing_bars"])

    freq_alias = {"1m": "T", "5m": "5T", "15m": "15T", "30m": "30T", "1h": "H", "1d": "B"}.get(
        interval, "B"
    )

    rows: list[dict] = []
    for sym, g in df.groupby("symbol"):
        idx = pd.DatetimeIndex(g["ts"])
        expected = pd.date_range(idx.min(), idx.max(), freq=freq_alias, tz=idx.tz)
        missing = expected.difference(idx)
        if len(missing) == 0:
            continue
        # Collapse contiguous missing periods
        diffs = missing.to_series().diff()
        breaks = (diffs > diffs.min()).cumsum() if not diffs.empty else None
        if breaks is None:
            continue
        for _, grp in missing.to_series().groupby(breaks):
            rows.append(
                {
                    "symbol": sym,
                    "gap_start": grp.iloc[0],
                    "gap_end": grp.iloc[-1],
                    "missing_bars": len(grp),
                }
            )
    return pd.DataFrame(rows)
