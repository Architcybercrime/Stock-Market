"""Tests for risk profiles."""

from __future__ import annotations

import pytest

from services.daemon.profiles import PROFILES, RiskProfile, RiskProfileName, get_profile


def test_all_profiles_valid():
    for p in PROFILES.values():
        p.validate()


def test_weights_sum_to_one():
    for p in PROFILES.values():
        s = p.weight_momentum + p.weight_mean_reversion + p.weight_ml
        assert 0.99 <= s <= 1.01, f"{p.name} weights sum to {s}"


def test_get_profile_by_string():
    p = get_profile("balanced")
    assert p.name == RiskProfileName.BALANCED


def test_aggressive_is_more_invested_than_conservative():
    c = PROFILES[RiskProfileName.CONSERVATIVE]
    a = PROFILES[RiskProfileName.AGGRESSIVE]
    assert a.target_invested_pct > c.target_invested_pct
    assert a.max_positions > c.max_positions
    assert a.max_position_pct > c.max_position_pct


def test_aggressive_has_higher_ml_weight():
    c = PROFILES[RiskProfileName.CONSERVATIVE]
    a = PROFILES[RiskProfileName.AGGRESSIVE]
    assert a.weight_ml > c.weight_ml


def test_opportunity_profile_is_adaptive():
    o = PROFILES[RiskProfileName.OPPORTUNITY]
    assert o.opportunity_adaptive is True
    assert o.max_positions >= 12, "opportunity ceiling should be >= aggressive"
    # Non-opportunity profiles are NOT adaptive.
    for name in [RiskProfileName.CONSERVATIVE, RiskProfileName.BALANCED, RiskProfileName.AGGRESSIVE]:
        assert PROFILES[name].opportunity_adaptive is False


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        RiskProfile(
            name=RiskProfileName.BALANCED,
            target_invested_pct=0.5,
            max_positions=3,
            max_position_pct=0.05,
            min_position_pct=0.01,
            weight_momentum=0.5,
            weight_mean_reversion=0.5,
            weight_ml=0.5,  # sum = 1.5
            rebalance_threshold_pct=0.01,
            min_confidence=0.5,
            use_volatility_targeting=False,
            vol_target_annual=0.15,
            description="",
        ).validate()
