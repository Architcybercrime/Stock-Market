"""Symbol and timestamp normalization for cross-source consistency."""

from __future__ import annotations

import pandas as pd


# Cross-source symbol aliases. Extend as new sources are added.
_SYMBOL_ALIASES: dict[str, str] = {
    # FX
    "EUR-USD": "EURUSD",
    "EUR/USD": "EURUSD",
    # Indices that vendors write differently
    "^GSPC": "SPX",
    "^DJI": "DJI",
    "^IXIC": "IXIC",
    "^VIX": "VIX",
    # Berkshire
    "BRK-B": "BRK.B",
}


def normalize_symbol(symbol: str) -> str:
    """Map vendor-specific tickers to our canonical form."""
    s = symbol.strip().upper()
    return _SYMBOL_ALIASES.get(s, s)


def normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Apply symbol + timestamp normalization in place-safe fashion.

    - Canonicalizes symbol via the alias map
    - Ensures `ts` is UTC tz-aware
    - Strips duplicate rows on (symbol, ts), keeping the first
    """
    if df.empty:
        return df

    df = df.copy()
    df["symbol"] = df["symbol"].map(normalize_symbol)

    if not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    else:
        df["ts"] = df["ts"].dt.tz_convert("UTC")

    df = df.drop_duplicates(subset=["symbol", "ts"], keep="first")
    df = df.sort_values(["symbol", "ts"]).reset_index(drop=True)
    return df
