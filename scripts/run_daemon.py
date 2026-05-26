"""Start the autonomous paper-trading daemon.

Defaults to the INDIAN MARKET (NSE) with Indian cost model. Pass --market NYSE
to switch to US equities (requires changing the universe too).

Broker selection (auto, override with --broker):
- For India: always LocalPaperBroker (no Zerodha/Upstox integration yet).
- For US:    Alpaca if ALPACA_API_KEY is set, else LocalPaperBroker.

State (LocalPaperBroker) persists in data/paper_state.json. In the GitHub
Actions deploy this file is committed back to the repo after each run.

Usage:
    python scripts/run_daemon.py                                  # interactive
    python scripts/run_daemon.py --profile balanced
    python scripts/run_daemon.py --profile conservative --run-once
    python scripts/run_daemon.py --market NYSE --universe AAPL MSFT GOOG

Safety:
    - Always paper. Live mode requires LIVE_TRADING_ENABLED=true AND
      a wired live-broker integration (Zerodha/Upstox for India; not yet
      shipped).
    - Kill switch checked before every order submission.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from services.daemon.profiles import RiskProfileName, get_profile, prompt_for_profile
from services.daemon.runner import TradingDaemon
from services.daemon.scheduler import run_forever

log = get_logger("run_daemon")


# Indian Nifty 50 + a couple of liquid ETFs. All available via yfinance
# with the .NS (NSE) suffix.
NSE_UNIVERSE = [
    # Large-cap private banks
    "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "AXISBANK.NS",
    # Public-sector banks
    "SBIN.NS",
    # IT
    "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS",
    # Energy + materials
    "RELIANCE.NS", "ONGC.NS", "TATASTEEL.NS",
    # Auto
    "MARUTI.NS", "TATAMOTORS.NS", "M&M.NS",
    # Consumer
    "HINDUNILVR.NS", "ITC.NS", "ASIANPAINT.NS", "NESTLEIND.NS",
    # Pharma + healthcare
    "SUNPHARMA.NS", "DRREDDY.NS",
    # Telecom
    "BHARTIARTL.NS",
    # Cement + infra
    "ULTRACEMCO.NS", "LT.NS",
    # NBFC + Insurance
    "BAJFINANCE.NS", "BAJAJFINSV.NS",
    # ETFs (broad market exposure)
    "NIFTYBEES.NS",     # Nifty 50 ETF
    "BANKBEES.NS",      # Nifty Bank ETF
]

# Same code can trade US markets — kept here for opt-in via --market NYSE.
US_UNIVERSE = [
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
        print("    For India you also need a wired Zerodha/Upstox broker — not yet shipped.")
        print("    Type 'I UNDERSTAND' to continue, anything else aborts.")
        confirm = input("> ").strip()
        if confirm != "I UNDERSTAND":
            print("Aborted.")
            sys.exit(2)
    else:
        print("\n[mode] paper trading — no real money will be moved.")


def _build_broker_and_source(broker_choice: str, market: str, initial_cash: float):
    """Pick broker + data source for the chosen market."""
    from services.backtest.costs import CostModel, IndianEquityCostModel, SlippageModel

    is_india = market in ("NSE", "BSE")

    # India: no broker integration yet. Force local paper.
    if is_india and broker_choice == "alpaca":
        raise RuntimeError("Alpaca does not support Indian markets. Use --broker local or auto.")

    has_alpaca = bool(settings.alpaca_api_key and settings.alpaca_api_secret)

    if not is_india and (broker_choice == "alpaca" or (broker_choice == "auto" and has_alpaca)):
        from services.execution.brokers.alpaca import AlpacaBroker
        from services.ingestion.sources.alpaca_source import AlpacaSource

        broker = AlpacaBroker()
        source = AlpacaSource()
        return broker, source, f"alpaca (paper={broker.is_paper})"

    # LocalPaperBroker + chained free data sources.
    # India: NSE bhavcopy (official, no rate limits) → yfinance fallback.
    # US:    yfinance only (bhavcopy is NSE-specific).
    from services.execution.brokers.local_paper import LocalPaperBroker
    from services.ingestion.sources.chained import ChainedSource
    from services.ingestion.sources.yfinance_source import YFinanceSource

    if is_india:
        from services.ingestion.sources.nse_bhavcopy import NSEBhavcopySource
        source = ChainedSource([NSEBhavcopySource(), YFinanceSource()])
    else:
        source = YFinanceSource()
    state_path = Path(settings.data_root) / "paper_state.json"

    cost_model = IndianEquityCostModel() if is_india else CostModel()
    broker = LocalPaperBroker(
        state_path=state_path,
        price_source=source,
        initial_cash=initial_cash,
        cost_model=cost_model,
        slippage_model=SlippageModel(),
    )
    label = f"local_paper [{market}] (state={state_path.resolve()})"
    return broker, source, label


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the autonomous trading daemon")
    parser.add_argument(
        "--profile",
        choices=[p.value for p in RiskProfileName],
        default=None,
        help="Risk profile. Prompts interactively if omitted and stdin is a TTY.",
    )
    parser.add_argument(
        "--market",
        choices=["NSE", "BSE", "NYSE"],
        default="NSE",
        help="Market to trade. Default: NSE (Indian).",
    )
    parser.add_argument(
        "--universe",
        nargs="+",
        default=None,
        help="Override the default symbol list. Default: Nifty-50 subset for NSE, S&P top for NYSE.",
    )
    parser.add_argument(
        "--broker",
        choices=["auto", "alpaca", "local"],
        default="auto",
        help="Broker. India always uses 'local'; US uses Alpaca if keys set.",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=1_000_000.0,
        help="Starting cash. For India in INR (default 10 lakh); for US in USD.",
    )
    parser.add_argument("--run-once", action="store_true", help="Run a single cycle and exit (no scheduler)")
    parser.add_argument("--history-bars", type=int, default=260)
    parser.add_argument(
        "--timeframe",
        default="1d",
        choices=["1d", "1h", "30m", "15m"],
        help=(
            "Bar timeframe. Default 1d (daily). Intraday timeframes trade more "
            "often but have higher cost drag and worse-tested behavior — only "
            "use if you understand the trade-off."
        ),
    )
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)
    _confirm_paper_mode()

    if args.profile:
        profile = get_profile(args.profile)
    else:
        profile = prompt_for_profile()
    print(f"\n[profile] {profile.name.value}: {profile.description}\n")

    # Universe defaults by market
    if args.universe is not None:
        universe = args.universe
    elif args.market in ("NSE", "BSE"):
        universe = NSE_UNIVERSE
    else:
        universe = US_UNIVERSE

    try:
        broker, source, broker_label = _build_broker_and_source(args.broker, args.market, args.initial_cash)
    except Exception as exc:
        print(f"!! could not start broker/source: {exc}", file=sys.stderr)
        return 2

    currency = "INR" if args.market in ("NSE", "BSE") else "USD"
    print(f"[market]    {args.market} (currency: {currency})")
    print(f"[broker]    {broker_label}")
    print(f"[timeframe] {args.timeframe}{'  [intraday — higher cost drag]' if args.timeframe != '1d' else ''}")
    print(
        f"[universe]  {len(universe)} symbols: "
        f"{' '.join(universe[:6])}{'...' if len(universe) > 6 else ''}"
    )

    daemon = TradingDaemon(
        broker=broker,
        data_source=source,
        profile=profile,
        universe=universe,
        history_bars=args.history_bars,
        timeframe=args.timeframe,
    )

    if args.run_once:
        report = daemon.run_once()
        sym = "₹" if currency == "INR" else "$"
        print(
            f"\n[result] nav={sym}{report.nav:,.2f} "
            f"selected={report.n_selected} attempted={report.n_orders_attempted} "
            f"accepted={report.n_orders_accepted} rejected={report.n_orders_rejected}"
        )
        if report.aggregator_result:
            print("\n[selected positions]")
            for c in report.aggregator_result.selected:
                tw = report.aggregator_result.target_weights.get(c.symbol, 0.0)
                print(f"  {c.symbol:14s}  target_weight={tw:.2%}  conf={c.confidence:.2f}  {c.rationale}")
        return 0 if report.error is None else 1

    print(f"\n[scheduler] waiting for next {args.market} market close. Ctrl-C to stop.\n")
    run_forever(daemon, market=args.market)
    return 0


if __name__ == "__main__":
    sys.exit(main())
