"""yfinance-backed data source.

yfinance returns split- and dividend-adjusted close prices when
auto_adjust=True. We use that for the OHLC and keep the raw close in
a sidecar column for reference. yfinance is fine for research; do not
use it as the source of truth for live trading.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from libs.common.logging import get_logger
from libs.common.time_utils import to_utc
from services.ingestion.sources.base import DataSource

log = get_logger(__name__)


class YFinanceSource(DataSource):
    name = "yfinance"

    # yfinance interval aliases
    _INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "60m",
        "1d": "1d",
        "1wk": "1wk",
        "1mo": "1mo",
    }

    def __init__(self, auto_adjust: bool = True) -> None:
        self.auto_adjust = auto_adjust

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        import yfinance as yf

        yf_interval = self._INTERVAL_MAP.get(interval, interval)

        log.info(
            "yfinance.fetch",
            symbol=symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            interval=yf_interval,
        )
        df = yf.download(
            tickers=symbol,
            start=start,
            end=end,
            interval=yf_interval,
            auto_adjust=self.auto_adjust,
            actions=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            log.warning("yfinance.empty", symbol=symbol)
            return self._empty_frame()

        # yfinance returns a MultiIndex columns frame when multiple tickers
        # are passed; we only pass one, so flatten if needed.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index().rename(
            columns={
                "Date": "ts",
                "Datetime": "ts",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        df["ts"] = df["ts"].apply(to_utc)
        df["symbol"] = symbol
        df["interval"] = interval
        df["adjusted"] = bool(self.auto_adjust)
        df = df[["ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted"]]
        df = df.sort_values("ts").reset_index(drop=True)
        return df

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=["ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted"]
        )

    def latest_close(self, symbol: str) -> float | None:
        """Most recent daily close. Used by LocalPaperBroker for fill prices."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        df = self.fetch_bars(symbol, now - timedelta(days=10), now, "1d")
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])
