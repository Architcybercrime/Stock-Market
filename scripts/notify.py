"""Send a Telegram message about the latest daemon activity.

Setup (one-time, ~3 min):
  1. On Telegram, message @BotFather:
       /newbot
     follow prompts to name your bot. It returns a token like
       123456789:ABCdefGhIJKlmNoPQRstUVWXYZ
  2. Start a chat with your new bot (search for it by username, send /start).
  3. Get your chat id: visit https://api.telegram.org/bot<TOKEN>/getUpdates
     in a browser. Look for "chat":{"id": NUMBER, ...}.
  4. In the GitHub repo, Settings -> Secrets and variables -> Actions -> New
     secret. Add:
       TELEGRAM_BOT_TOKEN = <token from BotFather>
       TELEGRAM_CHAT_ID   = <chat id you found>

If either secret is unset, this script is a no-op (exit 0, prints a hint).
That way the workflow never fails on missing notifications setup.

Usage in workflow:
    python scripts/notify.py --state data/paper_state.json --kind trade-cycle
    python scripts/notify.py --kind error --message "yfinance fetch failed"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path


def _send(text: str) -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print("Telegram secrets not set; skipping notification.", file=sys.stderr)
        print("See scripts/notify.py header for setup steps.", file=sys.stderr)
        return 0

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                print(f"telegram: HTTP {resp.status}", file=sys.stderr)
                return 1
    except Exception as exc:
        print(f"telegram: send failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _format_trade_cycle(state: dict) -> str:
    currency = state.get("currency", "INR")
    sym = "₹" if currency == "INR" else "$"
    cash = float(state.get("cash", "0") or 0)
    initial = float(state.get("initial_capital", "1") or 1)
    mtm = float(state.get("mark_to_market_equity") or cash)
    positions = state.get("positions") or {}
    avg_costs = state.get("avg_costs") or {}
    last_prices = state.get("last_prices") or {}
    fills = state.get("fills") or []

    # Compute today's NAV change from equity_history.
    eq = state.get("equity_history") or []
    today_change = 0.0
    if len(eq) >= 2:
        try:
            today_change = float(eq[-1][1]) - float(eq[-2][1])
        except Exception:
            pass

    # Most-recent fills (today's commits).
    snap_ts = state.get("snapshot_at") or state.get("updated_at") or ""
    today_fills = []
    for f in fills[-30:]:
        if f.get("ts", "")[:10] == snap_ts[:10]:
            today_fills.append(f)

    total_return_pct = ((mtm - initial) / initial) * 100 if initial > 0 else 0.0

    lines = [
        f"*📊 Daemon cycle complete*",
        f"NAV: `{sym}{mtm:,.2f}` ({total_return_pct:+.2f}% all-time)",
        f"Today: `{today_change:+,.0f}`",
        f"Cash: `{sym}{cash:,.0f}` | Positions: `{len(positions)}`",
    ]
    if today_fills:
        lines.append("")
        lines.append(f"*New trades ({len(today_fills)}):*")
        for f in today_fills[:8]:
            qty = float(f.get("qty", 0))
            price = float(f.get("price", 0))
            side = (f.get("side") or "").upper()
            lines.append(f"  {side} `{f.get('symbol', '?')}` × {qty:.0f} @ {sym}{price:.2f}")
        if len(today_fills) > 8:
            lines.append(f"  …+{len(today_fills) - 8} more")
    else:
        lines.append("")
        lines.append("_No trades this cycle._")

    if positions:
        lines.append("")
        lines.append("*Top positions:*")
        ranked = []
        for s, q_str in positions.items():
            qty = float(q_str)
            px = float(last_prices.get(s) or avg_costs.get(s) or 0)
            ranked.append((s, qty * px))
        ranked.sort(key=lambda x: x[1], reverse=True)
        for s, val in ranked[:5]:
            lines.append(f"  `{s}` ≈ {sym}{val:,.0f}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["trade-cycle", "snapshot", "error", "raw"], required=True)
    parser.add_argument("--state", default="data/paper_state.json")
    parser.add_argument("--message", default="")
    args = parser.parse_args(argv)

    if args.kind == "trade-cycle":
        path = Path(args.state)
        if not path.exists():
            return _send(f"⚠️ Daemon cycle ran but no state file at `{path}`.")
        state = json.loads(path.read_text())
        return _send(_format_trade_cycle(state))

    if args.kind == "snapshot":
        path = Path(args.state)
        if not path.exists():
            return _send(f"⚠️ Snapshot ran but no state file at `{path}`.")
        state = json.loads(path.read_text())
        currency = state.get("currency", "INR")
        sym = "₹" if currency == "INR" else "$"
        mtm = float(state.get("mark_to_market_equity") or 0)
        return _send(f"📈 Snapshot refresh: NAV `{sym}{mtm:,.2f}`")

    if args.kind == "error":
        msg = args.message or "Unknown error"
        return _send(f"🚨 *Daemon error*\n```\n{msg[:1000]}\n```")

    # raw
    return _send(args.message or "(empty)")


if __name__ == "__main__":
    sys.exit(main())
