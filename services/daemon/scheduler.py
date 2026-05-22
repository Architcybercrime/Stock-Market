"""Daily-at-market-close scheduler.

Supports multiple markets via the MARKET env variable (or `market` argument):

    NSE   -- National Stock Exchange of India. Close 15:30 IST = 10:00 UTC.
    BSE   -- Bombay Stock Exchange. Same schedule as NSE for our purposes.
    NYSE  -- New York Stock Exchange. Close 16:00 ET = 20:00 (EDT) or 21:00 (EST) UTC.

Computes the next market close, sleeps until ~5 minutes after, then runs one
daemon cycle. Skips weekends and exchange-specific holidays via
pandas-market-calendars when available; otherwise falls back to a fixed
weekday schedule.

This in-process loop is fine for paper trading. For production scaling, run
under systemd / k8s CronJob / GitHub Actions cron so process restarts don't
leave gaps.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from libs.common.logging import get_logger
from services.daemon.runner import TradingDaemon

log = get_logger(__name__)


# Per-market metadata used in the fallback path (when pandas_market_calendars
# isn't installed or fails).
_MARKET_CONFIG: dict[str, dict] = {
    "NSE": {
        "tz": "Asia/Kolkata",
        "close_hour": 15,
        "close_minute": 30,
        "calendar": "NSE",       # pandas_market_calendars id
    },
    "BSE": {
        "tz": "Asia/Kolkata",
        "close_hour": 15,
        "close_minute": 30,
        "calendar": "BSE",
    },
    "NYSE": {
        "tz": "America/New_York",
        "close_hour": 16,
        "close_minute": 0,
        "calendar": "NYSE",
    },
}


def _resolve_market(market: str | None) -> str:
    if market:
        m = market.upper()
    else:
        m = os.environ.get("MARKET", "NSE").upper()
    if m not in _MARKET_CONFIG:
        raise ValueError(f"unsupported market: {m}. Choose NSE, BSE, or NYSE.")
    return m


def _next_close(now_utc: datetime, *, market: str, run_offset_minutes: int = 5) -> datetime:
    """Return the next exchange close + offset, in UTC. Skips weekends + holidays."""
    cfg = _MARKET_CONFIG[market]

    # Try the proper calendar first.
    try:
        import pandas_market_calendars as mcal

        cal = mcal.get_calendar(cfg["calendar"])
        schedule = cal.schedule(
            start_date=now_utc.date(),
            end_date=(now_utc + timedelta(days=14)).date(),
        )
        for _, row in schedule.iterrows():
            close_utc = row["market_close"].to_pydatetime()
            if close_utc.tzinfo is None:
                close_utc = close_utc.replace(tzinfo=UTC)
            else:
                close_utc = close_utc.astimezone(UTC)
            target = close_utc + timedelta(minutes=run_offset_minutes)
            if target > now_utc:
                return target
    except Exception as exc:
        log.warning("scheduler.calendar_unavailable", market=market, error=str(exc))

    # Fallback: fixed local-time close, skipping weekends only (no holidays).
    local_tz = ZoneInfo(cfg["tz"])
    now_local = now_utc.astimezone(local_tz)
    target_local = now_local.replace(
        hour=cfg["close_hour"],
        minute=cfg["close_minute"] + run_offset_minutes,
        second=0,
        microsecond=0,
    )
    if target_local <= now_local:
        target_local = target_local + timedelta(days=1)
    while target_local.weekday() >= 5:
        target_local = target_local + timedelta(days=1)
    return target_local.astimezone(UTC)


def run_forever(
    daemon: TradingDaemon,
    *,
    market: str | None = None,
    run_offset_minutes: int = 5,
) -> None:
    """Block forever, running the daemon once per market close."""
    market_id = _resolve_market(market)
    log.info("scheduler.start", profile=daemon.profile.name.value, market=market_id)

    while True:
        now = datetime.now(UTC)
        target = _next_close(now, market=market_id, run_offset_minutes=run_offset_minutes)
        wait_seconds = (target - now).total_seconds()
        log.info(
            "scheduler.waiting",
            market=market_id,
            next_run=target.isoformat(),
            wait_minutes=round(wait_seconds / 60, 1),
        )
        end = time.monotonic() + wait_seconds
        try:
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(60.0, remaining))
        except KeyboardInterrupt:
            log.info("scheduler.stopped_by_user")
            return

        try:
            report = daemon.run_once()
            log.info("scheduler.cycle_complete", nav=report.nav, n_accepted=report.n_orders_accepted)
        except Exception as exc:
            log.error("scheduler.cycle_failed", error=str(exc), exc_info=exc)
            time.sleep(60)
