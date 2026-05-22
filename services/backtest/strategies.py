"""Reference strategies. Each is intentionally simple — they exist to exercise
the engine, not to make money. Build serious strategies under your own module
and import the engine."""

from __future__ import annotations

from collections import deque

import pandas as pd

from services.backtest.engine import PortfolioSnapshot, Strategy, TargetOrder


class MomentumStrategy(Strategy):
    """Cross-sectional momentum: long the top-N symbols by trailing N-bar return.

    Per-symbol state: rolling close window. On each bar, computes momentum
    (close/close_lookback - 1). Once we have 1 bar per symbol per period, we
    rebalance to the top-K names equal-weighted. Rebalances every `rebalance`
    bars to limit turnover.
    """

    name = "momentum"

    def __init__(self, lookback: int = 20, top_k: int = 3, rebalance: int = 5) -> None:
        self.lookback = lookback
        self.top_k = top_k
        self.rebalance = rebalance
        self._bars_per_symbol: dict[str, deque[float]] = {}
        self._bar_count = 0
        self._symbols: list[str] = []
        self._last_rebalance = -1

    def on_start(self, symbols: list[str]) -> None:
        self._symbols = symbols
        for s in symbols:
            self._bars_per_symbol[s] = deque(maxlen=self.lookback + 1)

    def on_bar(self, bar: pd.Series, portfolio: PortfolioSnapshot) -> list[TargetOrder]:
        sym = bar["symbol"]
        self._bars_per_symbol[sym].append(float(bar["close"]))
        self._bar_count += 1

        # Only rebalance when ALL symbols have enough data and at least once per rebalance window.
        if not all(len(w) > self.lookback for w in self._bars_per_symbol.values()):
            return []
        if self._last_rebalance >= 0 and (self._bar_count - self._last_rebalance) < self.rebalance:
            return []

        # Use this rebalance opportunity once per "round" (once per symbol-cycle).
        # We approximate by rebalancing on the *last* symbol of each cycle.
        if sym != self._symbols[-1]:
            return []

        momentums: dict[str, float] = {}
        for s, w in self._bars_per_symbol.items():
            momentums[s] = w[-1] / w[0] - 1.0

        ranked = sorted(momentums.items(), key=lambda kv: kv[1], reverse=True)
        winners = {s for s, _ in ranked[: self.top_k] if momentums[s] > 0}

        # Target equal weight in winners, zero elsewhere.
        target_weight = 1.0 / max(len(winners), 1) if winners else 0.0
        orders: list[TargetOrder] = []
        equity = portfolio.equity
        for s in self._symbols:
            current_qty = portfolio.positions.get(s, 0.0)
            target_notional = equity * (target_weight if s in winners else 0.0)
            # Use last known price for sizing (the engine fills on next open with slippage).
            last_price = self._bars_per_symbol[s][-1]
            target_qty = target_notional / last_price if last_price > 0 else 0.0
            delta = target_qty - current_qty
            if abs(delta) * last_price < equity * 0.001:  # below 10 bps NAV — skip
                continue
            side = "buy" if delta > 0 else "sell"
            orders.append(TargetOrder(symbol=s, side=side, qty=abs(delta)))

        self._last_rebalance = self._bar_count
        return orders


class MeanReversionStrategy(Strategy):
    """Per-symbol mean reversion using z-score of close vs rolling mean."""

    name = "mean_reversion"

    def __init__(self, window: int = 20, entry_z: float = -2.0, exit_z: float = 0.0,
                 position_pct: float = 0.1) -> None:
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.position_pct = position_pct
        self._closes: dict[str, deque[float]] = {}

    def on_start(self, symbols: list[str]) -> None:
        for s in symbols:
            self._closes[s] = deque(maxlen=self.window)

    def on_bar(self, bar: pd.Series, portfolio: PortfolioSnapshot) -> list[TargetOrder]:
        sym = bar["symbol"]
        price = float(bar["close"])
        self._closes[sym].append(price)
        if len(self._closes[sym]) < self.window:
            return []

        series = pd.Series(list(self._closes[sym]))
        mu = series.mean()
        sigma = series.std()
        if sigma == 0 or pd.isna(sigma):
            return []
        z = (price - mu) / sigma
        current_qty = portfolio.positions.get(sym, 0.0)

        # Long-only mean reversion: buy when z very negative, exit on neutral.
        if current_qty == 0 and z <= self.entry_z:
            target_notional = portfolio.equity * self.position_pct
            qty = target_notional / price if price > 0 else 0.0
            return [TargetOrder(symbol=sym, side="buy", qty=qty)]
        if current_qty > 0 and z >= self.exit_z:
            return [TargetOrder(symbol=sym, side="sell", qty=current_qty)]
        return []


class SignalStrategy(Strategy):
    """Wraps an external signal generator. Used to backtest model outputs.

    Caller supplies a `signal_fn(symbol, bar, history) -> float in [-1, 1]`
    representing target weight. The strategy rebalances each bar to the target.
    """

    name = "signal"

    def __init__(self, signal_fn, history_len: int = 60, rebalance_threshold: float = 0.02) -> None:
        self.signal_fn = signal_fn
        self.history_len = history_len
        self.rebalance_threshold = rebalance_threshold
        self._history: dict[str, deque[pd.Series]] = {}

    def on_start(self, symbols: list[str]) -> None:
        for s in symbols:
            self._history[s] = deque(maxlen=self.history_len)

    def on_bar(self, bar: pd.Series, portfolio: PortfolioSnapshot) -> list[TargetOrder]:
        sym = bar["symbol"]
        self._history[sym].append(bar)
        if len(self._history[sym]) < self.history_len:
            return []
        target_weight = float(self.signal_fn(sym, bar, list(self._history[sym])))
        target_weight = max(-1.0, min(1.0, target_weight))

        price = float(bar["close"])
        current_qty = portfolio.positions.get(sym, 0.0)
        target_qty = (portfolio.equity * target_weight) / price if price > 0 else 0.0
        delta = target_qty - current_qty
        if abs(delta) * price < portfolio.equity * self.rebalance_threshold:
            return []
        side = "buy" if delta > 0 else "sell"
        return [TargetOrder(symbol=sym, side=side, qty=abs(delta))]
