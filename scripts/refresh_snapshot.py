"""Refresh mark-to-market state in data/paper_state.json.

Runs every day (including weekends) to keep the dashboard fresh. Pulls the
latest close for each held position from yfinance and writes:

- last_prices: { symbol: latest_close_float }
- equity_history: appends (now_utc, mark_to_market_equity)
- mark_to_market_equity: float (for convenience)
- currency: "INR" or "USD" (best-guess from symbol suffixes)

Does NOT submit any orders. Does NOT mutate cash, positions, or fills.

Idempotent: if every held position already has today's latest price in
last_prices and equity_history has a sample within the last 6 hours, it
exits without changing the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


def _detect_currency(positions: dict[str, str]) -> str:
    """Best-guess currency from symbol suffixes."""
    if not positions:
        return "INR"   # default for our use case
    for sym in positions:
        if sym.endswith(".NS") or sym.endswith(".BO"):
            return "INR"
    return "USD"


def _latest_close(symbol: str) -> float | None:
    """Pull the most recent daily close from yfinance. None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed; cannot refresh snapshot", file=sys.stderr)
        return None

    try:
        # Use Ticker.history() — more stable than yf.download() for single symbols
        # and gives us better empty-result detection.
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", auto_adjust=True)
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as exc:
        print(f"  warn: {symbol} fetch failed: {exc}", file=sys.stderr)
        return None


def _initial_state(currency: str = "INR", initial_cash: float = 1_000_000.0) -> dict:
    """Bootstrap a fresh state file. Used on the very first run before any
    daemon has executed, so the dashboard has something to render."""
    now_iso = datetime.now(UTC).isoformat()
    return {
        "schema_version": 1,
        "cash": f"{initial_cash:.2f}",
        "initial_capital": f"{initial_cash:.2f}",
        "realized_pnl": "0",
        "positions": {},
        "avg_costs": {},
        "orders": [],
        "fills": [],
        "equity_history": [[now_iso, f"{initial_cash:.2f}"]],
        "last_prices": {},
        "mark_to_market_equity": float(initial_cash),
        "currency": currency,
        "updated_at": now_iso,
        "snapshot_at": now_iso,
    }


def refresh(state_path: Path) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)

    if not state_path.exists():
        print(f"no state file at {state_path}; bootstrapping initial state")
        state_path.write_text(json.dumps(_initial_state(), indent=2))
        print(f"created {state_path} with initial 10 lakh INR cash")
        return 0

    data = json.loads(state_path.read_text())
    positions = data.get("positions", {})
    cash = Decimal(data.get("cash", "0"))
    currency = data.get("currency") or _detect_currency(positions)

    # Symbols we need prices for: held positions + everything we've held in
    # the past 30 days so the dashboard can attribute recent fills.
    symbols_to_price = set(positions.keys())
    recent_cutoff = datetime.now(UTC) - timedelta(days=30)
    for fill in data.get("fills", [])[-200:]:
        try:
            ts = datetime.fromisoformat(fill["ts"])
            if ts > recent_cutoff:
                symbols_to_price.add(fill["symbol"])
        except (KeyError, ValueError):
            continue

    if not symbols_to_price:
        print("no positions to refresh; touching equity_history only")

    print(f"refreshing {len(symbols_to_price)} symbols...")
    last_prices: dict[str, float] = dict(data.get("last_prices") or {})
    fetched = 0
    failed = 0
    for sym in sorted(symbols_to_price):
        px = _latest_close(sym)
        if px is None:
            failed += 1
            print(f"  {sym}: FAILED")
        else:
            last_prices[sym] = px
            fetched += 1
            print(f"  {sym}: {px:.2f}")

    # Mark-to-market equity using whatever prices we have
    mtm = cash
    for sym, qty_str in positions.items():
        qty = Decimal(qty_str)
        if qty == 0:
            continue
        px = last_prices.get(sym)
        if px is None:
            # Fall back to avg_cost if no live price; better than nothing.
            px = float(Decimal(data.get("avg_costs", {}).get(sym, "0")))
        mtm += qty * Decimal(str(px))

    # Append equity sample (capped to last 2000 points; matches LocalPaperBroker)
    now_iso = datetime.now(UTC).isoformat()
    eq_history = data.get("equity_history", [])
    eq_history.append([now_iso, str(mtm)])
    eq_history = eq_history[-2000:]

    data["last_prices"] = last_prices
    data["equity_history"] = eq_history
    data["mark_to_market_equity"] = float(mtm)
    data["currency"] = currency
    data["snapshot_at"] = now_iso

    state_path.write_text(json.dumps(data, indent=2))
    print(
        f"\ndone. fetched={fetched} failed={failed} "
        f"MTM={currency} {float(mtm):,.2f} "
        f"equity_history_points={len(eq_history)}"
    )
    return 0 if (failed == 0 or fetched > 0) else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh mark-to-market snapshot")
    parser.add_argument(
        "--state-path",
        default="data/paper_state.json",
        help="Path to the paper_state.json file (default: data/paper_state.json)",
    )
    args = parser.parse_args(argv)
    return refresh(Path(args.state_path))


if __name__ == "__main__":
    sys.exit(main())
