"""Performance metrics computed from an equity curve and fill log.

Metrics are computed from realized fills, not from the strategy's claimed P&L.
This protects against bugs in the strategy code or accidental lookahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(
    equity: pd.Series,
    fills: pd.DataFrame | None = None,
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Compute headline performance metrics from an equity series.

    `equity` must be indexed by bar time and contain total portfolio value.
    """
    if equity.empty or len(equity) < 2:
        return {}

    rets = equity.pct_change().dropna()
    log_rets = np.log(equity / equity.shift(1)).dropna()

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max(len(rets) / periods_per_year, 1e-9)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)

    ann_vol = float(rets.std() * np.sqrt(periods_per_year))
    excess_ret = rets - risk_free_rate / periods_per_year
    sharpe = float(excess_ret.mean() / (rets.std() + 1e-12) * np.sqrt(periods_per_year))

    downside = rets[rets < 0]
    sortino = (
        float(excess_ret.mean() / (downside.std() + 1e-12) * np.sqrt(periods_per_year))
        if not downside.empty
        else float("nan")
    )

    # Max drawdown
    cummax = equity.cummax()
    dd = equity / cummax - 1.0
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else float("inf")

    # Drawdown duration
    in_dd = dd < 0
    if in_dd.any():
        groups = (in_dd != in_dd.shift()).cumsum()[in_dd]
        if not groups.empty:
            max_dd_duration = int(groups.value_counts().max())
        else:
            max_dd_duration = 0
    else:
        max_dd_duration = 0

    metrics: dict[str, float] = {
        "total_return": total_return,
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "max_drawdown_duration_bars": float(max_dd_duration),
        "calmar": calmar,
        "n_periods": float(len(rets)),
    }

    if fills is not None and not fills.empty:
        # Per-trade stats from fills. Group fills into round-trips via FIFO.
        trade_stats = _round_trip_stats(fills)
        metrics.update(trade_stats)

    return metrics


def _round_trip_stats(fills: pd.DataFrame) -> dict[str, float]:
    """Estimate win rate and profit factor by pairing entries with exits FIFO.

    Assumes columns: symbol, side ('buy'/'sell'), qty, price, fee, ts.
    """
    required = {"symbol", "side", "qty", "price", "fee", "ts"}
    if not required.issubset(fills.columns):
        return {}

    pnls: list[float] = []
    open_lots: dict[str, list[tuple[float, float]]] = {}  # symbol -> [(qty, price)]

    for _, f in fills.sort_values("ts").iterrows():
        sym = f["symbol"]
        side = f["side"]
        qty = float(f["qty"])
        price = float(f["price"])
        fee = float(f["fee"])
        if sym not in open_lots:
            open_lots[sym] = []
        if side == "buy":
            open_lots[sym].append((qty, price))
        else:
            remaining = qty
            while remaining > 0 and open_lots[sym]:
                lot_qty, lot_price = open_lots[sym][0]
                take = min(remaining, lot_qty)
                pnl = (price - lot_price) * take - fee * (take / qty)
                pnls.append(pnl)
                remaining -= take
                if take == lot_qty:
                    open_lots[sym].pop(0)
                else:
                    open_lots[sym][0] = (lot_qty - take, lot_price)

    if not pnls:
        return {}

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    return {
        "n_round_trips": float(len(arr)),
        "win_rate": float(len(wins) / len(arr)) if len(arr) else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf"),
        "expectancy": float(arr.mean()),
    }
