"""Print a human-readable summary of the LocalPaperBroker state.

Use this to inspect data/paper_state.json without firing the daemon. Reads
the same file the workflow commits back after each run.

Usage:
    python scripts/show_portfolio.py
    python scripts/show_portfolio.py --state-path some/other/paper_state.json
    python scripts/show_portfolio.py --recent 10        # last N orders + fills
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from libs.common.config import settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect LocalPaperBroker state")
    parser.add_argument(
        "--state-path",
        default=str(Path(settings.data_root) / "paper_state.json"),
    )
    parser.add_argument("--recent", type=int, default=5, help="Show last N orders + fills")
    parser.add_argument("--currency", default="INR", choices=["INR", "USD"], help="Display currency symbol")
    args = parser.parse_args(argv)
    sym = "₹" if args.currency == "INR" else "$"

    path = Path(args.state_path)
    if not path.exists():
        print(f"no state file at {path}")
        print("nothing has been traded yet. run `python scripts/run_daemon.py --run-once` first.")
        # Not an error — pre-trade state is a valid state. Return 0 so CI does
        # not mark a fresh paper account as a failure.
        return 0

    data = json.loads(path.read_text())
    cash = Decimal(data["cash"])
    initial = Decimal(data["initial_capital"])
    realized = Decimal(data["realized_pnl"])
    positions = {s: Decimal(q) for s, q in data["positions"].items()}
    avg_costs = {s: Decimal(c) for s, c in data["avg_costs"].items()}

    print("=" * 60)
    print(" PAPER ACCOUNT SNAPSHOT")
    print("=" * 60)
    print(f" updated_at      : {data.get('updated_at', '?')}")
    print(f" initial capital : {sym}{float(initial):>14,.2f}")
    print(f" cash            : {sym}{float(cash):>14,.2f}")
    print(f" realized P&L    : {sym}{float(realized):>+14,.2f}")
    print()

    if positions:
        print(" Open positions:")
        print(f"  {'symbol':<8s} {'qty':>8s} {'avg cost':>12s} {'cost basis':>14s}")
        total_basis = Decimal(0)
        for sym, qty in sorted(positions.items()):
            cost = avg_costs.get(sym, Decimal(0))
            basis = qty * cost
            total_basis += basis
            print(f"  {sym:<8s} {float(qty):>8.2f} {float(cost):>12.2f} {float(basis):>14,.2f}")
        print(f"  {'TOTAL':<8s} {'':>8s} {'':>12s} {float(total_basis):>14,.2f}")
        equity_estimate = cash + total_basis
        print()
        print(f" approx equity (cash + basis) : {sym}{float(equity_estimate):>14,.2f}")
        print(f"   (real mark-to-market needs live prices; run the daemon for that)")
    else:
        print(" No open positions.")
    print()

    orders = data.get("orders", [])
    fills = data.get("fills", [])
    print(f" total orders submitted : {len(orders)}")
    print(f" total fills            : {len(fills)}")

    if orders and args.recent > 0:
        print(f"\n last {min(args.recent, len(orders))} orders:")
        print(f"  {'ts':<28s} {'symbol':<6s} {'side':<5s} {'qty':>6s} {'status':<12s} {'reason':<30s}")
        for o in orders[-args.recent:]:
            ts = o.get("created_at", "?")
            reason = (o.get("reject_reason") or "")[:30]
            print(
                f"  {ts[:24]:<28s} {o['symbol']:<6s} {o['side']:<5s} "
                f"{o['qty']:>6s} {o['status']:<12s} {reason:<30s}"
            )

    if fills and args.recent > 0:
        print(f"\n last {min(args.recent, len(fills))} fills:")
        print(f"  {'ts':<28s} {'symbol':<6s} {'side':<5s} {'qty':>6s} {'price':>10s} {'fee':>8s}")
        for f in fills[-args.recent:]:
            ts = f.get("ts", "?")
            print(
                f"  {ts[:24]:<28s} {f['symbol']:<6s} {f['side']:<5s} "
                f"{f['qty']:>6s} {f['price']:>10s} {f['fee']:>8s}"
            )

    # Equity history summary
    eq = data.get("equity_history", [])
    if eq:
        ts0, val0 = eq[0]
        ts_n, val_n = eq[-1]
        pct = (Decimal(val_n) / Decimal(val0) - 1) * 100 if Decimal(val0) > 0 else Decimal(0)
        print(f"\n equity series: {len(eq)} points")
        print(f"  first : {ts0[:24]}  {sym}{float(val0):,.2f}")
        print(f"  last  : {ts_n[:24]}  {sym}{float(val_n):,.2f}  ({float(pct):+.2f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
