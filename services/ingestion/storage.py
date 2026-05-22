"""Parquet-based local storage for ingested bars.

Partitioned as:
    data_root/bars/symbol={SYMBOL}/interval={INTERVAL}/year={YYYY}/data.parquet

This layout is friendly to predicate pushdown in pyarrow.dataset queries.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from libs.common.logging import get_logger

log = get_logger(__name__)


class BarStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "bars"
        self.root.mkdir(parents=True, exist_ok=True)

    def _partition_path(self, symbol: str, interval: str, year: int) -> Path:
        return self.root / f"symbol={symbol}" / f"interval={interval}" / f"year={year}"

    def write(self, df: pd.DataFrame) -> int:
        """Write/merge bars to per-(symbol, interval, year) parquet partitions.

        Duplicate rows by (ts) within a partition are deduped, keeping the
        latest ingested version. Returns total rows written across partitions.
        """
        if df.empty:
            return 0

        df = df.copy()
        df["year"] = pd.DatetimeIndex(df["ts"]).year
        written = 0

        for (sym, interval, year), part in df.groupby(["symbol", "interval", "year"]):
            partition = self._partition_path(sym, interval, int(year))
            partition.mkdir(parents=True, exist_ok=True)
            file_path = partition / "data.parquet"

            if file_path.exists():
                existing = pq.read_table(file_path).to_pandas()
                merged = pd.concat([existing, part], ignore_index=True)
                merged = merged.drop_duplicates(subset=["ts"], keep="last")
                merged = merged.sort_values("ts").reset_index(drop=True)
            else:
                merged = part.drop(columns=["year"], errors="ignore").sort_values("ts").reset_index(drop=True)

            # Drop the partition cols from the stored payload — they live in the path
            for col in ("year",):
                if col in merged.columns:
                    merged = merged.drop(columns=col)

            table = pa.Table.from_pandas(merged, preserve_index=False)
            pq.write_table(table, file_path, compression="snappy")
            written += len(merged)
            log.info("barstore.write", symbol=sym, interval=interval, year=int(year), rows=len(merged))

        return written

    def read(
        self,
        symbol: str,
        interval: str = "1d",
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Read bars for a symbol/interval, optionally bounded by time."""
        sym_path = self.root / f"symbol={symbol}" / f"interval={interval}"
        if not sym_path.exists():
            return pd.DataFrame()

        dataset = ds.dataset(sym_path, format="parquet", partitioning="hive")
        filters = None
        if start is not None:
            filters = ds.field("ts") >= pa.scalar(start)
        if end is not None:
            end_filter = ds.field("ts") <= pa.scalar(end)
            filters = end_filter if filters is None else filters & end_filter

        table = dataset.to_table(filter=filters) if filters is not None else dataset.to_table()
        df = table.to_pandas()
        if df.empty:
            return df
        df = df.sort_values("ts").reset_index(drop=True)
        return df
