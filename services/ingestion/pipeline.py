"""End-to-end ingestion pipeline: source -> validate -> normalize -> store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from libs.common.logging import get_logger
from services.ingestion.normalizer import normalize_bars
from services.ingestion.sources.base import DataSource
from services.ingestion.storage import BarStore
from services.ingestion.validation import validate_bars

log = get_logger(__name__)


class IngestionPipeline:
    def __init__(self, source: DataSource, data_root: Path, strict: bool = False) -> None:
        self.source = source
        self.store = BarStore(data_root)
        self.strict = strict

    def ingest_symbol(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> int:
        """Fetch -> validate -> normalize -> store. Returns rows written."""
        log.info("ingest.start", symbol=symbol, start=start.isoformat(), end=end.isoformat())
        raw = self.source.fetch_bars(symbol, start, end, interval)
        if raw.empty:
            log.warning("ingest.empty", symbol=symbol)
            return 0
        validated = validate_bars(raw, strict=self.strict)
        normalized = normalize_bars(validated)
        written = self.store.write(normalized)
        log.info("ingest.done", symbol=symbol, rows=written)
        return written

    def ingest_many(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> dict[str, int]:
        """Fetch many symbols sequentially. Errors per symbol do not abort the batch."""
        results: dict[str, int] = {}
        for sym in symbols:
            try:
                results[sym] = self.ingest_symbol(sym, start, end, interval)
            except Exception as exc:
                log.error("ingest.error", symbol=sym, exc_info=exc)
                results[sym] = -1
        return results
