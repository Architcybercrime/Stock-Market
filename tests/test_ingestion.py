"""Tests for the ingestion validation + normalizer + Parquet store."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.ingestion.normalizer import normalize_bars, normalize_symbol
from services.ingestion.storage import BarStore
from services.ingestion.validation import BarValidationError, validate_bars


def test_normalize_symbol_aliases():
    assert normalize_symbol("brk-b") == "BRK.B"
    assert normalize_symbol("^GSPC") == "SPX"
    assert normalize_symbol("AAPL") == "AAPL"


def test_validate_rejects_negative_volume(synthetic_bars):
    df = synthetic_bars.copy()
    df.loc[df.index[0], "volume"] = -1.0
    with pytest.raises(BarValidationError):
        validate_bars(df, strict=True)


def test_validate_rejects_inverted_high_low(synthetic_bars):
    df = synthetic_bars.copy()
    df.loc[df.index[0], "high"] = df.loc[df.index[0], "low"] - 1.0
    with pytest.raises(BarValidationError):
        validate_bars(df, strict=True)


def test_validate_non_strict_drops_bad_rows(synthetic_bars):
    df = synthetic_bars.copy()
    df.loc[df.index[0], "close"] = float("nan")
    out = validate_bars(df, strict=False)
    assert len(out) == len(df) - 1


def test_normalize_drops_duplicate_ts(synthetic_bars):
    df = pd.concat([synthetic_bars, synthetic_bars.head(5)], ignore_index=True)
    out = normalize_bars(df)
    assert len(out) == len(synthetic_bars)


def test_barstore_roundtrip(tmp_path: Path, synthetic_bars):
    store = BarStore(tmp_path)
    n = store.write(synthetic_bars)
    assert n > 0
    df = store.read("TEST", "1d")
    assert len(df) == len(synthetic_bars)


def test_barstore_merge_dedups(tmp_path: Path, synthetic_bars):
    store = BarStore(tmp_path)
    store.write(synthetic_bars)
    # Re-writing the same bars should not duplicate rows.
    store.write(synthetic_bars)
    df = store.read("TEST", "1d")
    assert len(df) == len(synthetic_bars)
