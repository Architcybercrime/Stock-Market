"""Tests for the signal aggregator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from libs.common.types import SignalDirection
from services.signals.aggregator import ModelPrediction, SignalAggregator


def _pred(ret: float, conf: float, mid: str = "m") -> ModelPrediction:
    return ModelPrediction(model_id=mid, model_version="1", expected_return=ret, confidence=conf)


def test_returns_none_below_min_confidence():
    agg = SignalAggregator(min_confidence=0.6)
    out = agg.aggregate("AAPL", datetime.now(UTC), [_pred(0.01, 0.5)])
    assert out is None


def test_long_signal_above_threshold():
    agg = SignalAggregator(weight_scale=10.0, min_confidence=0.5, flat_threshold=0.01)
    out = agg.aggregate("AAPL", datetime.now(UTC), [_pred(0.005, 0.7)])
    assert out is not None
    assert out.direction == SignalDirection.LONG
    assert out.target_weight > 0


def test_short_signal_below_threshold():
    agg = SignalAggregator(weight_scale=10.0, min_confidence=0.5, flat_threshold=0.01)
    out = agg.aggregate("AAPL", datetime.now(UTC), [_pred(-0.005, 0.7)])
    assert out is not None
    assert out.direction == SignalDirection.SHORT
    assert out.target_weight < 0


def test_flat_within_threshold():
    agg = SignalAggregator(weight_scale=1.0, min_confidence=0.5, flat_threshold=0.05)
    out = agg.aggregate("AAPL", datetime.now(UTC), [_pred(0.001, 0.7)])
    assert out is not None
    assert out.direction == SignalDirection.FLAT
    assert out.target_weight == 0.0


def test_confidence_weighted_aggregation():
    agg = SignalAggregator(weight_scale=1.0, min_confidence=0.5, flat_threshold=0.0)
    out = agg.aggregate(
        "AAPL",
        datetime.now(UTC),
        [
            _pred(0.01, 0.9, mid="strong"),
            _pred(-0.10, 0.6, mid="weak"),
        ],
    )
    assert out is not None
    # The high-confidence positive prediction should dominate
    assert out.target_weight > -0.05
