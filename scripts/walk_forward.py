"""Walk-forward backtest with fresh yfinance data.

Runs weekly to detect regime drift: re-run the daemon's strategies on the
last 6 months of bars and write the headline metrics to
`data/backtest_history.json`. The dashboard can then chart live equity
against this OOS-style baseline.

Not a true purged walk-forward (no train/test refitting of the ML model
here — the daemon's MomentumSignal is rules-based and stateless). Think
of this as a "what would momentum have done on this window" sanity check.

Output schema:
    [
      {
        "ts": "2026-05-26T13:00:00+00:00",
        "window_days": 180,
        "n_symbols": 21,
        "total_return_pct": 4.2,
        "cagr_pct": 8.6,
        "sharpe": 0.71,
        "max_drawdown_pct": -3.4
      },
      ...
    ]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


# Reusing the same default Indian universe the live daemon trades.
DEFAULT_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "NESTLEIND.NS",
    "WIPRO.NS", "BAJFINANCE.NS", "HCLTECH.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "NIFTYBEES.NS",
]

_YF_MAX_ATTEMPTS = 4
_YF_BACKOFF = 1.5


def _fetch_one(symbol: str, start: datetime, end: datetime) -> pd.DataFrame | None:
    import yfinance as yf

    for attempt in range(1, _YF_MAX_ATTEMPTS + 1):
        try:
            df = yf.download(
                tickers=symbol, start=start, end=end, interval="1d",
                auto_adjust=True, actions=False, progress=False, threads=False,
            )
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df
        except Exception:
            pass
        if attempt < _YF_MAX_ATTEMPTS:
            time.sleep(_YF_BACKOFF * (2 ** (attempt - 1)))
    return None


def _equal_weight_momentum(prices: dict[str, pd.DataFrame], top_k: int = 5, lookback: int = 20) -> pd.Series:
    """Equity curve of a simple long-only momentum: each rebalance pick top_k
    by trailing return, equal-weight, hold 5 sessions. Same shape as the
    daemon's MomentumSignal so the comparison is meaningful."""
    # Align all closes on a common date index
    closes = pd.DataFrame({s: df["Close"] for s, df in prices.items()}).dropna(how="all")
    closes = closes.sort_index()
    if closes.shape[0] < lookback + 5:
        return pd.Series(dtype=float)

    rets = closes.pct_change().fillna(0)
    weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)

    rebalance_every = 5
    last_holdings: list[str] = []
    for i, dt in enumerate(closes.index):
        if i < lookback:
            continue
        if (i - lookback) % rebalance_every == 0:
            trailing = closes.iloc[i] / closes.iloc[i - lookback] - 1
            picks = trailing.dropna().nlargest(top_k).index.tolist()
            last_holdings = picks
        if last_holdings:
            w = 1.0 / len(last_holdings)
            for s in last_holdings:
                weights.at[dt, s] = w

    # Daily portfolio return = previous-day weights · today's returns
    port_ret = (weights.shift(1).fillna(0) * rets).sum(axis=1)
    equity = (1.0 + port_ret).cumprod()
    return equity


def _metrics(equity: pd.Series) -> dict[str, float]:
    if equity.empty or len(equity) < 2:
        return {"total_return_pct": 0.0, "cagr_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0}
    total_ret = float(equity.iloc[-1] - 1.0)
    days = (equity.index[-1] - equity.index[0]).days or 1
    cagr = (equity.iloc[-1]) ** (365.25 / days) - 1
    rets = equity.pct_change().dropna()
    sharpe = float((rets.mean() / rets.std()) * (252 ** 0.5)) if rets.std() > 0 else 0.0
    running_max = equity.cummax()
    dd = (equity / running_max - 1).min()
    return {
        "total_return_pct": round(total_ret * 100, 4),
        "cagr_pct": round(float(cagr) * 100, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": round(float(dd) * 100, 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward backtest cron")
    parser.add_argument("--window-days", type=int, default=180)
    parser.add_argument("--out", default="data/backtest_history.json")
    parser.add_argument("--universe", nargs="+", default=None)
    args = parser.parse_args(argv)

    universe = args.universe or DEFAULT_UNIVERSE
    end = datetime.now(UTC)
    start = end - timedelta(days=args.window_days + 30)  # buffer for lookback

    print(f"walk_forward: fetching {len(universe)} symbols, last {args.window_days}d...")
    prices: dict[str, pd.DataFrame] = {}
    failed = 0
    for sym in universe:
        df = _fetch_one(sym, start, end)
        if df is None or df.empty:
            failed += 1
            print(f"  {sym}: FAILED", file=sys.stderr)
        else:
            prices[sym] = df

    if len(prices) < 5:
        print(f"walk_forward: only {len(prices)} symbols fetched; aborting", file=sys.stderr)
        return 2

    equity = _equal_weight_momentum(prices)
    if equity.empty:
        print("walk_forward: not enough bars for backtest", file=sys.stderr)
        return 2

    metrics = _metrics(equity)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "window_days": args.window_days,
        "n_symbols": len(prices),
        "n_failed": failed,
        **metrics,
    }
    print("walk_forward:", json.dumps(metrics))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if out_path.exists():
        try:
            history = json.loads(out_path.read_text())
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append(entry)
    history = history[-104:]  # ~2 years of weekly samples
    out_path.write_text(json.dumps(history, indent=2))
    print(f"walk_forward: wrote {out_path} (history size: {len(history)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
