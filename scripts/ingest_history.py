"""Pull historical bars from yfinance and store as Parquet.

Example:
    python scripts/ingest_history.py --symbols AAPL MSFT SPY --start 2018-01-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from libs.common.time_utils import to_utc
from services.ingestion.pipeline import IngestionPipeline
from services.ingestion.sources.yfinance_source import YFinanceSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest historical bars to local Parquet store")
    parser.add_argument("--symbols", nargs="+", required=True, help="Tickers to ingest")
    parser.add_argument("--start", default="2020-01-01", help="ISO date, e.g. 2020-01-01")
    parser.add_argument("--end", default=None, help="ISO date; defaults to today")
    parser.add_argument("--interval", default="1d", help="1d, 1h, 5m, etc.")
    parser.add_argument("--strict", action="store_true", help="Fail on any validation issue")
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)
    log = get_logger("ingest_history")

    start = to_utc(args.start)
    end = to_utc(args.end) if args.end else datetime.now(UTC)

    pipeline = IngestionPipeline(
        source=YFinanceSource(),
        data_root=settings.data_root,
        strict=args.strict,
    )
    results = pipeline.ingest_many(args.symbols, start, end, args.interval)

    failures = [s for s, n in results.items() if n < 0]
    log.info("ingest_history.done", results=results, failures=failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
