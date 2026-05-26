"""Append a human-readable trade journal entry from paper_state.json.

Run after each daemon cycle. Reads the state file, identifies fills from
*this UTC date* that are not already in the journal, and appends a
markdown row to journal/YYYY-MM.md.

The journal is the source of truth for "what did the bot do, and why"
when you read it 3 months later. Strategies, profile, NAV, and per-fill
side/qty/price/fee get one line each.

Idempotent: if today's fills are already journaled, the script is a no-op.

Layout:
    journal/
      2026-05.md
      2026-06.md
      ...

The journal/ directory is committed alongside data/ so the dashboard repo
serves as the audit trail too.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path


def _today_fills(state: dict) -> list[dict]:
    today_iso = datetime.now(UTC).date().isoformat()
    out = []
    for f in (state.get("fills") or [])[-200:]:
        ts = f.get("ts", "")
        if ts[:10] == today_iso:
            out.append(f)
    return out


def _existing_fill_ids(journal_path: Path) -> set[str]:
    """Pull fill ids already written to today's journal section so we don't
    duplicate. We embed them as HTML comments per row."""
    if not journal_path.exists():
        return set()
    ids: set[str] = set()
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        # marker comment looks like:  <!-- fill:abc123 -->
        idx = line.find("<!-- fill:")
        if idx >= 0:
            tail = line[idx + len("<!-- fill:"):]
            end = tail.find(" -->")
            if end > 0:
                ids.add(tail[:end])
    return ids


def append_today(state_path: Path, journal_dir: Path) -> int:
    if not state_path.exists():
        print(f"journal: no state at {state_path}", file=sys.stderr)
        return 2
    state = json.loads(state_path.read_text())

    fills_today = _today_fills(state)
    if not fills_today:
        print("journal: no fills today; nothing to append")
        return 0

    today = date.today()
    journal_dir.mkdir(parents=True, exist_ok=True)
    j_path = journal_dir / f"{today.strftime('%Y-%m')}.md"

    already = _existing_fill_ids(j_path)
    new_fills = [f for f in fills_today if f.get("id") not in already]
    if not new_fills:
        print("journal: all of today's fills already journaled")
        return 0

    cur = state.get("currency", "INR")
    sym = "INR" if cur == "INR" else "USD"
    mtm = float(state.get("mark_to_market_equity") or 0)
    initial = float(state.get("initial_capital") or 1)
    ret = ((mtm - initial) / initial * 100) if initial > 0 else 0.0
    n_positions = len(state.get("positions") or {})

    lines = []
    if not j_path.exists():
        lines.append(f"# Trade journal — {today.strftime('%B %Y')}\n")

    lines.append(f"\n## {today.isoformat()}  ·  NAV {sym} {mtm:,.0f}  ({ret:+.2f}% all-time)  ·  {n_positions} positions")
    lines.append("")
    lines.append("| time UTC | side | symbol | qty | price | fee | order id |")
    lines.append("| -------- | ---- | ------ | ---:| -----:| ---:| -------- |")

    for f in new_fills:
        ts = f.get("ts", "")[:19].replace("T", " ")
        side = (f.get("side") or "").upper()
        qty = float(f.get("qty", 0))
        price = float(f.get("price", 0))
        fee = float(f.get("fee", 0))
        oid = f.get("order_id", "")[:8]
        fill_id = f.get("id", "")
        lines.append(
            f"| {ts} | {side} | `{f.get('symbol', '?')}` | {qty:.0f} | {price:,.2f} | {fee:.2f} | `{oid}` |"
            f" <!-- fill:{fill_id} -->"
        )

    with j_path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"journal: appended {len(new_fills)} fills to {j_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a trade journal entry")
    parser.add_argument("--state", default="data/paper_state.json")
    parser.add_argument("--journal-dir", default="journal")
    args = parser.parse_args(argv)
    return append_today(Path(args.state), Path(args.journal_dir))


if __name__ == "__main__":
    sys.exit(main())
