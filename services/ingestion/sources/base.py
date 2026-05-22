"""Data source abstraction.

A source returns a normalized DataFrame with these columns:
    ts (datetime, UTC)
    symbol (str)
    open, high, low, close, volume (float)
    interval (str)
    adjusted (bool)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

REQUIRED_COLUMNS = ["ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted"]


class DataSource(ABC):
    """Base class for all market-data sources."""

    name: str = "base"

    @abstractmethod
    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return a DataFrame with REQUIRED_COLUMNS, sorted by ts ascending.

        Implementations MUST:
        - Return UTC timestamps
        - Mark adjusted=True if split/dividend-adjusted
        - Return an empty DataFrame (with the right columns) when no data exists
        - Raise on transport errors (let the caller decide retry policy)
        """

    def fetch_many(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch multiple symbols. Default impl is serial; override for parallel."""
        return {s: self.fetch_bars(s, start, end, interval) for s in symbols}
