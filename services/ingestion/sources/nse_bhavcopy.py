"""NSE bhavcopy data source.

The official daily NSE/BSE EOD file. Free, no API key, no rate limits,
maintained by the exchange — a much more reliable primary source than
yfinance for Indian equities.

URL pattern (changes occasionally; using the post-2024 archive endpoint):
    https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv

Each file is one trading day; columns include SYMBOL, SERIES, OPEN, HIGH,
LOW, CLOSE, LAST, PREV_CLOSE, TOTTRDQTY, TURNOVER, NO_OF_TRADES,
DELIV_QTY, DELIV_PER, ...

This source only supports interval='1d' — the daemon already trades on
daily close so that's fine. yfinance remains the source for intraday or
for non-NSE markets via the ChainedSource fallback.

Holidays/weekends: NSE returns 404 for those days. We retry the previous
trading day rather than failing, so e.g. a Monday fetch over a 3-day
weekend still returns Friday's bar.
"""

from __future__ import annotations

import io
import time
from datetime import UTC, datetime, timedelta

import pandas as pd

from libs.common.logging import get_logger
from services.ingestion.sources.base import DataSource

log = get_logger(__name__)

# Strip the .NS / .BO suffix yfinance adds; NSE bhavcopy uses bare tickers.
_SUFFIX_STRIP = (".NS", ".BO", ".BSE", ".NSE")

_BASE_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
_HEADERS = {
    # NSE blocks default urllib UA; mimic a browser.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_MAX_ATTEMPTS = 3
_BACKOFF = 1.5


class NSEBhavcopySource(DataSource):
    name = "nse_bhavcopy"

    def __init__(self) -> None:
        # Tiny in-process cache keyed by date: one HTTP fetch per day per process.
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ fetch
    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            log.debug("nse_bhavcopy.unsupported_interval", interval=interval)
            return self._empty_frame()

        bare = self._strip_suffix(symbol)
        # Walk each calendar day in [start, end], skip weekends, fetch the
        # bhavcopy, filter to this symbol, accumulate rows.
        rows: list[dict] = []
        d = start.date()
        end_d = end.date()
        while d <= end_d:
            if d.weekday() < 5:   # 0=Mon ... 4=Fri
                day_df = self._fetch_day(d)
                if day_df is not None and not day_df.empty:
                    hit = day_df[day_df["SYMBOL"] == bare]
                    if not hit.empty:
                        r = hit.iloc[0]
                        rows.append({
                            "ts": pd.Timestamp(d, tz="UTC"),
                            "symbol": symbol,
                            "open": float(r["OPEN_PRICE"]),
                            "high": float(r["HIGH_PRICE"]),
                            "low": float(r["LOW_PRICE"]),
                            "close": float(r["CLOSE_PRICE"]),
                            "volume": float(r["TTL_TRD_QNTY"]),
                            "interval": "1d",
                            "adjusted": False,
                        })
            d += timedelta(days=1)

        if not rows:
            return self._empty_frame()
        df = pd.DataFrame(rows)
        return df.sort_values("ts").reset_index(drop=True)

    def latest_close(self, symbol: str) -> float | None:
        """Most recent close. Walks back up to 7 calendar days to skip holidays."""
        bare = self._strip_suffix(symbol)
        d = datetime.now(UTC).date()
        for _ in range(8):
            if d.weekday() < 5:
                day_df = self._fetch_day(d)
                if day_df is not None and not day_df.empty:
                    hit = day_df[day_df["SYMBOL"] == bare]
                    if not hit.empty:
                        return float(hit.iloc[0]["CLOSE_PRICE"])
            d -= timedelta(days=1)
        return None

    # ------------------------------------------------------------------ http

    def _fetch_day(self, d) -> pd.DataFrame | None:
        key = d.isoformat()
        if key in self._cache:
            return self._cache[key]

        url = _BASE_URL.format(ddmmyyyy=d.strftime("%d%m%Y"))
        import urllib.error
        import urllib.request

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                req = urllib.request.Request(url, headers=_HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status != 200:
                        return None
                    body = resp.read().decode("utf-8", errors="ignore")
                df = pd.read_csv(io.StringIO(body))
                # NSE column headers have whitespace padding — strip it.
                df.columns = [c.strip() for c in df.columns]
                # Keep only EQ series (cash equity); drop SME / debt / etc.
                if "SERIES" in df.columns:
                    df = df[df["SERIES"].str.strip() == "EQ"].copy()
                # Some columns come with whitespace in values too.
                if "SYMBOL" in df.columns:
                    df["SYMBOL"] = df["SYMBOL"].str.strip()
                self._cache[key] = df
                return df
            except urllib.error.HTTPError as exc:
                # 404 = no file for that date (holiday/weekend/early date).
                # Don't retry, just return None — caller walks to prior day.
                if exc.code == 404:
                    self._cache[key] = pd.DataFrame()
                    return None
                last_err = str(exc)
            except Exception as exc:
                last_err = str(exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF * (2 ** (attempt - 1)))

        log.warning("nse_bhavcopy.fetch_failed", date=key, error=last_err)
        return None

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _strip_suffix(symbol: str) -> str:
        for sfx in _SUFFIX_STRIP:
            if symbol.endswith(sfx):
                return symbol[: -len(sfx)]
        return symbol

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=["ts", "symbol", "open", "high", "low", "close", "volume", "interval", "adjusted"]
        )
