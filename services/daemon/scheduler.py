"""Daily-at-market-close scheduler.

Computes the next US market close (4:00 PM America/New_York), sleeps until
about 5 minutes before, then waits for the official close to publish and
runs the daemon. Skips weekends and US market holidays via
pandas-market-calendars.

The scheduler is intentionally simple — for production use you'd run this
under systemd / kubernetes CronJob / a cloud scheduler so process restarts
don't leave gaps. This in-process loop is fine for the paper-trading phase.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from libs.common.logging import get_logger
from services.daemon.runner import TradingDaemon

log = get_logger(__name__)

NY = ZoneInfo("America/New_York")


def _next_close(now_utc: datetime, run_offset_minutes: int = 5) -> datetime:
    """Return the next NYSE close + offset (so we run after the print settles).

    Returns a UTC datetime. Skips weekends + US trading holidays.
    """
    try:
        import pandas_market_calendars as mcal

        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(
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
        # Fallback if calendar empty
    except Exception as exc:
        log.warning("scheduler.calendar_unavailable", error=str(exc))

    # Fallback: naive 4:05 PM ET, skipping weekends.
    now_ny = now_utc.astimezone(NY)
    target_ny = now_ny.replace(hour=16, minute=run_offset_minutes, second=0, microsecond=0)
    if target_ny <= now_ny:
        target_ny = target_ny + timedelta(days=1)
    while target_ny.weekday() >= 5:
        target_ny = target_ny + timedelta(days=1)
    return target_ny.astimezone(UTC)


def run_forever(daemon: TradingDaemon, run_offset_minutes: int = 5) -> None:
    """Block forever, running the daemon once per market close."""
    log.info("scheduler.start", profile=daemon.profile.name.value)
    while True:
        now = datetime.now(UTC)
        target = _next_close(now, run_offset_minutes)
        wait_seconds = (target - now).total_seconds()
        log.info(
            "scheduler.waiting",
            next_run=target.isoformat(),
            wait_minutes=round(wait_seconds / 60, 1),
        )
        # Sleep in chunks so KeyboardInterrupt is responsive
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
            # Backoff before next attempt to avoid hot-looping on persistent errors.
            time.sleep(60)
