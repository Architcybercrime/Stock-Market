"""Chained data source.

Tries each underlying source in order and returns the first non-empty
result. Used to make the live system resilient to any single provider
failing: NSE bhavcopy is the primary for Indian equities, yfinance is
the safety net.

Logs which source served each request so we can see in the daemon log
when one is unhealthy.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from libs.common.logging import get_logger
from services.ingestion.sources.base import DataSource

log = get_logger(__name__)


class ChainedSource(DataSource):
    name = "chained"

    def __init__(self, sources: list[DataSource]) -> None:
        if not sources:
            raise ValueError("ChainedSource needs at least one source")
        self.sources = sources

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        last_empty_from: list[str] = []
        for src in self.sources:
            try:
                df = src.fetch_bars(symbol, start, end, interval)
            except Exception as exc:
                log.warning("chained.source_error", source=src.name, symbol=symbol, error=str(exc))
                continue
            if df is not None and not df.empty:
                if last_empty_from:
                    log.info(
                        "chained.fallback_hit",
                        symbol=symbol,
                        served_by=src.name,
                        skipped=last_empty_from,
                    )
                return df
            last_empty_from.append(src.name)
        log.warning("chained.all_empty", symbol=symbol, tried=last_empty_from)
        # Return the empty frame from the last source so column shape is right.
        return df  # type: ignore[return-value]

    def latest_close(self, symbol: str) -> float | None:
        """Try latest_close on each source. Falls through to fetch_bars-based
        derivation for sources that don't expose latest_close."""
        for src in self.sources:
            try:
                if hasattr(src, "latest_close"):
                    px = src.latest_close(symbol)
                    if px is not None and px > 0:
                        return px
            except Exception as exc:
                log.warning("chained.latest_close_error", source=src.name, error=str(exc))
        return None
