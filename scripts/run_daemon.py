"""Start the autonomous paper-trading daemon.

Interactive on first run: prompts you to pick a risk profile, confirms paper
mode, and shows the symbol universe. Then runs once per market close.

Usage:
    python scripts/run_daemon.py                       # interactive
    python scripts/run_daemon.py --profile balanced --universe AAPL MSFT GOOG
    python scripts/run_daemon.py --profile aggressive --run-once    # for testing

Safety:
    - Defaults to paper trading. Will refuse to switch to live without
      LIVE_TRADING_ENABLED=true AND TRADING_MODE=live in .env.
    - Checks the kill switch file before every order.
    - Logs every decision before it acts on it.
"""

from __future__ import annotations

import argparse
import sys

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from services.daemon.profiles import RiskProfileName, get_profile, prompt_for_profile
from services.daemon.runner import TradingDaemon
from services.daemon.scheduler import run_forever
from services.execution.brokers.alpaca import AlpacaBroker
from services.ingestion.sources.alpaca_source import AlpacaSource

log = get_logger("run_daemon")


DEFAULT_UNIVERSE = [
    # Large-cap, liquid US equities + a few ETFs. Good starter universe for
    # paper trading: covers tech, finance, healthcare, energy, broad market.
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "JPM", "BAC", "JNJ", "UNH",
    "XOM", "CVX",
    "SPY", "QQQ", "IWM",
]


def _confirm_paper_mode() -> None:
    if settings.trading_mode != "paper" or settings.live_trading_enabled:
        print("\n!!  LIVE TRADING MODE DETECTED  !!")
        print(f"    trading_mode={settings.trading_mode}")
        print(f"    live_trading_enabled={settings.live_trading_enabled}")
        print("    This script will place REAL orders against REAL money.")
        print("    Type 'I UNDERSTAND' to continue, anything else aborts.")
        confirm = input("> ").strip()
        if confirm != "I UNDERSTAND":
            print("Aborted.")
            sys.exit(2)
    else:
        print("\n[mode] paper trading — no real money will be moved.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the autonomous trading daemon")
    parser.add_argument(
        "--profile",
        choices=[p.value for p in RiskProfileName],
        default=None,
        help="Risk profile. Prompts interactively if omitted and stdin is a TTY.",
    )
    parser.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE)
    parser.add_argument("--run-once", action="store_true", help="Run a single cycle and exit (no scheduler)")
    parser.add_argument("--history-bars", type=int, default=260)
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)
    _confirm_paper_mode()

    # Pick profile
    if args.profile:
        profile = get_profile(args.profile)
    else:
        profile = prompt_for_profile()
    print(f"\n[profile] {profile.name.value}: {profile.description}\n")

    # Build broker + data source
    try:
        broker = AlpacaBroker()
    except Exception as exc:
        print(f"!! could not start Alpaca broker: {exc}", file=sys.stderr)
        return 2
    try:
        source = AlpacaSource()
    except Exception as exc:
        print(f"!! could not start Alpaca data source: {exc}", file=sys.stderr)
        return 2

    print(f"[broker] alpaca (paper={broker.is_paper})")
    print(f"[universe] {len(args.universe)} symbols: {' '.join(args.universe[:8])}{'...' if len(args.universe) > 8 else ''}")

    daemon = TradingDaemon(
        broker=broker,
        data_source=source,
        profile=profile,
        universe=args.universe,
        history_bars=args.history_bars,
    )

    if args.run_once:
        report = daemon.run_once()
        print(
            f"\n[result] nav=${report.nav:.2f} "
            f"selected={report.n_selected} attempted={report.n_orders_attempted} "
            f"accepted={report.n_orders_accepted} rejected={report.n_orders_rejected}"
        )
        if report.aggregator_result:
            print("\n[selected positions]")
            for c in report.aggregator_result.selected:
                tw = report.aggregator_result.target_weights.get(c.symbol, 0.0)
                print(f"  {c.symbol:6s}  target_weight={tw:.2%}  conf={c.confidence:.2f}  {c.rationale}")
        return 0 if report.error is None else 1

    print("\n[scheduler] waiting for next US market close. Ctrl-C to stop.\n")
    run_forever(daemon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
