"""Tests for IndianEquityCostModel."""

from __future__ import annotations

import pytest

from services.backtest.costs import IndianEquityCostModel


def test_brokerage_capped_at_20_rupees():
    model = IndianEquityCostModel()
    # A ₹10 lakh buy: 0.03% would be ₹300, but cap is ₹20
    fee = model.fee(notional=1_000_000.0, is_sell=False)
    # Total = brokerage (capped 20) + stamp (150) + exchange (~32) + sebi (~1) + GST
    # = 20 + 150 + 32.2 + 1 + 18% * (20 + 32.2) = 20 + 150 + 32.2 + 1 + 9.4 = ~212.6
    assert 200 <= fee <= 230


def test_sell_includes_stt():
    model = IndianEquityCostModel()
    sell_fee = model.fee(notional=100_000.0, is_sell=True)
    buy_fee = model.fee(notional=100_000.0, is_sell=False)
    # STT on sell = ₹100 (0.1% of 1L). Sell drops stamp duty (₹15).
    # Net diff = 100 - 15 = ₹85. Sell side should be meaningfully larger.
    assert sell_fee - buy_fee >= 75
    assert sell_fee > 100


def test_buy_includes_stamp_but_no_stt():
    model = IndianEquityCostModel()
    buy_fee = model.fee(notional=100_000.0, is_sell=False)
    # Stamp on 1L = ₹15. Brokerage ₹20 (capped). Exchange ~₹3.22. SEBI ~₹0.10.
    # GST 18% on (₹20 + ₹3.22) = ₹4.18
    # Total ~₹42.50
    assert 35 <= buy_fee <= 50


def test_round_trip_cost_in_expected_range():
    model = IndianEquityCostModel()
    notional = 100_000.0
    rt = model.fee(notional, is_sell=False) + model.fee(notional, is_sell=True)
    # Expected: ~₹170 = ~0.17% of ₹100k
    assert 150 <= rt <= 200


def test_small_trade_floor_behaviour():
    """Brokerage scales DOWN for small trades (not floored, no min fee)."""
    model = IndianEquityCostModel()
    # ₹5,000 trade: 0.03% = ₹1.50; min(1.50, 20) = ₹1.50
    fee = model.fee(notional=5_000.0, is_sell=False)
    # brokerage 1.50 + stamp 0.75 + exchange ~0.16 + sebi ~0.005 + GST ~0.30 = ~2.7
    assert 1.5 <= fee <= 5.0
