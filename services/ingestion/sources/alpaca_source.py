"""Alpaca-backed market data source.

Uses the free IEX feed by default (sufficient for daily-close trading).
Upgrade to SIP for full-tape coverage by setting `feed="sip"`.

Note: Alpaca returns split/dividend-adjusted bars when adjustment is
requested. We default to "raw" + we do our own adjustment downstream if
needed — but for the daemon's daily-close use case we use adjusted bars
because that's what the model was trained on.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from libs.common.config import settings
from libs.common.logging import get_logger
from libs.common.time_utils import to_utc
from services.ingestion.sources.base import DataSource

log = get_logger(__name__)


class AlpacaSource(DataSource):
    """Pulls bars from Alpaca's market data API.

    Requires ALPACA_API_KEY + ALPACA_API_SECRET in env. Free tier is fine.
    """

    name = "alpaca"

    _INTERVAL_MAP = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "30m": "30Min",
        "1h": "1Hour",
        "1d": "1Day",
    }

    def __init__(self, feed: str = "iex", adjustment: str = "all") -> None:
        if not (settings.alpaca_api_key and settings.alpaca_api_secret):
            raise RuntimeError(
                "AlpacaSource requires ALPACA_API_KEY + ALPACA_API_SECRET in .env. "
                "Sign up at https://alpaca.markets (free) and paste the keys."
            )
        from alpaca.data.historical import StockHistoricalDataClient

        self._client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key.get_secret_value(),
            secret_key=settings.alpaca_api_secret.get_secret_value(),
        )
        self.feed = feed
        self.adjustment = adjustment

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        # Map our interval to Alpaca's TimeFrame
        tf_map = {
            "1m": TimeFrame(1, TimeFrameUnit.Minute),
            "5m": TimeFrame(5, TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "30m": TimeFrame(30, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        if interval not in tf_map:
            raise ValueError(f"unsupported interval for Alpaca: {interval}")

        feed_enum = DataFeed.IEX if self.feed == "iex" else DataFeed.SIP
        adj_enum = {
            "raw": Adjustment.RAW,
            "split": Adjustment.SPLIT,
            "dividend": Adjustment.DIVIDEND,
            "all": Adjustment.ALL,
        }[self.adjustment]

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf_map[interval],
            start=start,
            end=end,
            feed=feed_enum,
            adjustment=adj_enum,
        )
        log.info("alpaca.fetch", symbol=symbol, interval=interval, feed=self.feed)
        bars = self._client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            log.warning("alpaca.empty", symbol=symbol)
            return self._empty_frame()

        # Alpaca returns a MultiIndex (symbol, timestamp). Flatten.
        df = df.reset_index()
        df = df.rename(
            columns={
                "timestamp": "ts",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
        )
        if "symbol" not in df.columns:
            df["symbol"] = symbol
        df["ts"] = df["ts"].apply(to_utc)
        df["interval"] = interval
        df["adjusted"] = self.adjustment != "raw"
        df = df[
            ["ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted"]
        ]
        return df.sort_values("ts").reset_index(drop=True)

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted",
            ]
        )

    def latest_close(self, symbol: str) -> float | None:
        """Convenience: fetch the most recent daily close for a symbol."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        df = self.fetch_bars(symbol, now - timedelta(days=10), now, "1d")
        if df.empty:
            return None
        return float(df["close"].iloc[-1])
