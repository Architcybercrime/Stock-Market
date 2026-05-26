"""Heartbeat / freshness alarm.

Reads data/paper_state.json, checks how long since its last update, and
fires a Telegram alarm via scripts/notify.py if it's stale.

"Stale" = `updated_at` (or `snapshot_at` if newer) older than --max-hours.

Default --max-hours is 30: the snapshot refresher runs every ~12 hours,
so 30h gives one full miss of buffer before we alarm. The daemon-only
silence is fine on weekends.

Exit codes:
  0 — fresh
  1 — stale (alarm fired)
  2 — no state file
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alarm if state file is stale")
    parser.add_argument("--state", default="data/paper_state.json")
    parser.add_argument("--max-hours", type=float, default=30.0)
    args = parser.parse_args(argv)

    path = Path(args.state)
    if not path.exists():
        msg = f"state file missing at {path}"
        print(f"heartbeat: {msg}", file=sys.stderr)
        _notify_error(msg)
        return 2

    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        msg = f"state file unreadable: {exc}"
        print(f"heartbeat: {msg}", file=sys.stderr)
        _notify_error(msg)
        return 2

    candidates = [_parse_ts(data.get("snapshot_at")), _parse_ts(data.get("updated_at"))]
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        msg = "state file has no updated_at/snapshot_at"
        print(f"heartbeat: {msg}", file=sys.stderr)
        _notify_error(msg)
        return 2

    latest = max(candidates)
    age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600.0
    print(f"heartbeat: last update {latest.isoformat()} ({age_hours:.1f}h ago)")

    if age_hours > args.max_hours:
        msg = (
            f"state stale: {age_hours:.1f}h since last update "
            f"(threshold {args.max_hours:.0f}h). Check the Actions tab — "
            f"likely yfinance failure or git push permission."
        )
        print(f"heartbeat: {msg}", file=sys.stderr)
        _notify_error(msg)
        return 1

    return 0


def _notify_error(message: str) -> None:
    """Fire-and-forget Telegram error via notify.py. Silent if secrets unset."""
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        return
    notify = Path(__file__).parent / "notify.py"
    try:
        subprocess.run(
            [sys.executable, str(notify), "--kind", "error", "--message", message],
            check=False,
            timeout=15,
        )
    except Exception as exc:
        print(f"heartbeat: notify failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
