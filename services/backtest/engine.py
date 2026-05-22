"""Event-driven backtester.

The engine iterates bars in chronological order. On each bar:
1. The strategy receives the *closed* bar and the current portfolio snapshot.
2. The strategy emits zero or more target orders.
3. Orders fill on the NEXT bar's open with cost + slippage applied. This is the
   simplest realistic model — no "fill at close on signal day" cheating.
4. The portfolio marks-to-market at each bar's close.

Multi-symbol: bars from all symbols are interleaved by timestamp. The strategy
sees one bar at a time but can maintain per-symbol state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd

from libs.common.logging import get_logger
from services.backtest.costs import CostModel, SlippageModel
from services.backtest.metrics import compute_metrics

log = get_logger(__name__)


@dataclass
class TargetOrder:
    """Strategies emit these; the engine turns them into fills."""

    symbol: str
    side: str         # "buy" | "sell"
    qty: float        # number of shares (positive)
    limit_price: float | None = None


@dataclass
class PortfolioSnapshot:
    """What a strategy sees about its current state."""

    cash: float
    positions: dict[str, float]    # symbol -> qty (negative = short)
    avg_cost: dict[str, float]     # symbol -> average cost basis
    equity: float
    bar_index: int
    ts: pd.Timestamp


class Strategy(ABC):
    """Strategies implement on_bar; they receive each closed bar and emit orders."""

    name: str = "base"

    def on_start(self, symbols: list[str]) -> None:
        """Hook called once before the first bar."""

    @abstractmethod
    def on_bar(self, bar: pd.Series, portfolio: PortfolioSnapshot) -> list[TargetOrder]:
        """Called per bar. Return a list of orders to submit on the next open."""

    def on_finish(self) -> None:
        """Hook called once after the last bar."""


@dataclass
class BacktestResult:
    equity: pd.Series
    fills: pd.DataFrame
    orders: pd.DataFrame
    metrics: dict[str, float] = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        initial_cash: float = 100_000.0,
        cost_model: CostModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> None:
        self.initial_cash = initial_cash
        self.cost_model = cost_model or CostModel()
        self.slippage_model = slippage_model or SlippageModel()

    def run(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """Run a backtest on a {symbol: OHLCV DataFrame} dict.

        Each DataFrame must have columns: ts, open, high, low, close, volume.
        """
        if not data:
            raise ValueError("no data")

        # Build a unified, time-sorted stream: (ts, symbol, row)
        rows = []
        for sym, df in data.items():
            if df.empty:
                continue
            df_sorted = df.sort_values("ts").reset_index(drop=True)
            for _, r in df_sorted.iterrows():
                rows.append((r["ts"], sym, r))
        rows.sort(key=lambda x: (x[0], x[1]))

        symbols = sorted(data.keys())
        strategy.on_start(symbols)

        cash = self.initial_cash
        positions: dict[str, float] = {s: 0.0 for s in symbols}
        avg_cost: dict[str, float] = {s: 0.0 for s in symbols}
        last_prices: dict[str, float] = {s: float("nan") for s in symbols}
        pending: list[tuple[str, TargetOrder]] = []  # (submitted_ts, order)

        equity_records: list[tuple[pd.Timestamp, float]] = []
        fills_records: list[dict] = []
        orders_records: list[dict] = []

        # 5-day rolling ADV cache per symbol; recomputed when we see new bars.
        adv_window: dict[str, list[float]] = {s: [] for s in symbols}

        for idx, (ts, sym, bar) in enumerate(rows):
            # 1) Execute pending orders for THIS symbol at THIS open.
            still_pending: list[tuple[str, TargetOrder]] = []
            for sub_ts, order in pending:
                if order.symbol != sym:
                    still_pending.append((sub_ts, order))
                    continue
                if sub_ts == ts:
                    # Same-bar order; defer (we already submitted at bar close).
                    still_pending.append((sub_ts, order))
                    continue
                fill_price, fee, filled_qty = self._execute(order, bar, adv_window[sym])
                if filled_qty == 0:
                    orders_records.append(
                        {**order.__dict__, "ts_submitted": sub_ts, "status": "rejected", "ts": ts}
                    )
                    continue
                signed_qty = filled_qty if order.side == "buy" else -filled_qty
                # Update cash
                cash -= signed_qty * fill_price + fee
                # Update position and average cost
                old_qty = positions[sym]
                new_qty = old_qty + signed_qty
                if old_qty == 0 or (old_qty > 0) != (new_qty > 0):
                    avg_cost[sym] = fill_price if new_qty != 0 else 0.0
                elif abs(new_qty) > abs(old_qty):
                    # Adding to existing direction — weighted average
                    avg_cost[sym] = (
                        avg_cost[sym] * abs(old_qty) + fill_price * abs(signed_qty)
                    ) / abs(new_qty)
                # Reducing: avg_cost unchanged
                positions[sym] = new_qty
                fills_records.append({
                    "ts": ts,
                    "symbol": sym,
                    "side": order.side,
                    "qty": filled_qty,
                    "price": fill_price,
                    "fee": fee,
                })
                orders_records.append(
                    {**order.__dict__, "ts_submitted": sub_ts, "status": "filled",
                     "ts": ts, "fill_price": fill_price, "fee": fee}
                )
            pending = still_pending

            # 2) Update last price + ADV window
            last_prices[sym] = float(bar["close"])
            adv_window[sym].append(float(bar["volume"]))
            if len(adv_window[sym]) > 5:
                adv_window[sym].pop(0)

            # 3) Mark equity at this bar's close
            mtm = cash + sum(
                positions[s] * (last_prices[s] if not np.isnan(last_prices[s]) else 0.0)
                for s in symbols
            )
            equity_records.append((ts, mtm))

            # 4) Ask the strategy for orders (using this bar's CLOSE info only)
            snap = PortfolioSnapshot(
                cash=cash,
                positions=dict(positions),
                avg_cost=dict(avg_cost),
                equity=mtm,
                bar_index=idx,
                ts=ts,
            )
            new_orders = strategy.on_bar(bar, snap) or []
            for o in new_orders:
                pending.append((ts, o))
                orders_records.append(
                    {**o.__dict__, "ts_submitted": ts, "status": "pending", "ts": ts}
                )

        strategy.on_finish()

        equity = pd.Series(
            [v for _, v in equity_records],
            index=pd.DatetimeIndex([t for t, _ in equity_records], name="ts"),
            name="equity",
        )
        # Collapse to per-bar (last value if multiple symbols share a ts).
        equity = equity.groupby(level=0).last()

        fills = pd.DataFrame(fills_records)
        orders = pd.DataFrame(orders_records)
        result_metrics = compute_metrics(equity, fills if not fills.empty else None)

        log.info(
            "backtest.complete",
            n_bars=len(rows),
            n_fills=len(fills),
            n_orders=len(orders),
            final_equity=float(equity.iloc[-1]) if not equity.empty else self.initial_cash,
            **{k: v for k, v in result_metrics.items() if k in {"sharpe", "max_drawdown", "cagr"}},
        )

        return BacktestResult(equity=equity, fills=fills, orders=orders, metrics=result_metrics)

    def _execute(
        self, order: TargetOrder, bar: pd.Series, adv_history: list[float]
    ) -> tuple[float, float, float]:
        """Determine fill price + fee for an order against the next bar."""
        intended = order.limit_price if order.limit_price is not None else float(bar["open"])
        adv = float(np.mean(adv_history)) if adv_history else None
        is_buy = order.side == "buy"

        # Limit-order rejection: if limit can't be touched in the bar range, no fill.
        if order.limit_price is not None:
            if is_buy and bar["low"] > order.limit_price:
                return 0.0, 0.0, 0.0
            if not is_buy and bar["high"] < order.limit_price:
                return 0.0, 0.0, 0.0

        fill_price = self.slippage_model.apply(intended, order.qty, adv, is_buy=is_buy)
        notional = order.qty * fill_price
        fee = self.cost_model.fee(notional, is_sell=not is_buy)
        return fill_price, fee, order.qty
