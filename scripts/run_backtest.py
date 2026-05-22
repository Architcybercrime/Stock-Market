"""Run a backtest with the event-driven engine.

Examples:
    python scripts/run_backtest.py --strategy momentum --symbols AAPL MSFT SPY
    python scripts/run_backtest.py --strategy mean_reversion --symbols AAPL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from services.backtest.engine import BacktestEngine
from services.backtest.strategies import MeanReversionStrategy, MomentumStrategy
from services.ingestion.storage import BarStore

log = get_logger("run_backtest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a backtest")
    parser.add_argument("--strategy", default="momentum", choices=["momentum", "mean_reversion"])
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--out", default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)

    # Load bars per symbol
    store = BarStore(Path(settings.data_root))
    data: dict[str, pd.DataFrame] = {}
    for sym in args.symbols:
        df = store.read(sym, args.interval)
        if df.empty:
            log.error("no_data_for_symbol", symbol=sym)
            return 2
        data[sym] = df

    # Build strategy
    if args.strategy == "momentum":
        strategy = MomentumStrategy(lookback=20, top_k=min(3, len(args.symbols)), rebalance=5)
    else:
        strategy = MeanReversionStrategy()

    engine = BacktestEngine(initial_cash=args.initial_cash)
    result = engine.run(strategy, data)

    log.info("backtest.final", **{k: v for k, v in result.metrics.items() if k in {"sharpe", "cagr", "max_drawdown", "total_return"}})

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump(
                {
                    "strategy": args.strategy,
                    "symbols": args.symbols,
                    "metrics": result.metrics,
                    "n_fills": int(len(result.fills)),
                    "n_orders": int(len(result.orders)),
                    "final_equity": float(result.equity.iloc[-1]) if not result.equity.empty else None,
                },
                f,
                indent=2,
                default=str,
            )
        log.info("backtest.report_written", path=str(out_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
