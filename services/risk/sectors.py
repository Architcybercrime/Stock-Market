"""Static sector classification for the live Indian universe.

A real production system would pull this from NSE's industry mapping or
ISIN-level reference data. For our zero-cost paper system, a hand-maintained
map covering the Nifty 50 + a few extras is plenty — these names don't
move sectors and the daemon's universe is small.

The aggregator + risk module use this to enforce RISK_MAX_SECTOR_PCT
(default 0.30): no more than 30% of NAV in any one sector. Without this
the cap exists in config but never bites.

When adding a new symbol to the daemon universe, add it here too. If
unknown, `sector_for("UNK.NS")` returns "Other" — the cap still applies
under the catch-all bucket, so missing a symbol is conservative-failing.
"""

from __future__ import annotations

# Sectors loosely follow NSE's industry classification, simplified.
NSE_SECTOR_MAP: dict[str, str] = {
    # Banking & financials
    "HDFCBANK.NS":    "Financials",
    "ICICIBANK.NS":   "Financials",
    "SBIN.NS":        "Financials",
    "KOTAKBANK.NS":   "Financials",
    "AXISBANK.NS":    "Financials",
    "BAJFINANCE.NS":  "Financials",
    "BAJAJFINSV.NS":  "Financials",
    "INDUSINDBK.NS":  "Financials",
    "HDFC.NS":        "Financials",
    "HDFCLIFE.NS":    "Financials",
    "SBILIFE.NS":     "Financials",
    "ICICIPRULI.NS":  "Financials",

    # IT / tech
    "TCS.NS":         "IT",
    "INFY.NS":        "IT",
    "WIPRO.NS":       "IT",
    "HCLTECH.NS":     "IT",
    "TECHM.NS":       "IT",
    "LTIM.NS":        "IT",

    # Energy / oil & gas
    "RELIANCE.NS":    "Energy",
    "ONGC.NS":        "Energy",
    "BPCL.NS":        "Energy",
    "IOC.NS":         "Energy",
    "COALINDIA.NS":   "Energy",
    "NTPC.NS":        "Energy",
    "POWERGRID.NS":   "Energy",
    "TATAPOWER.NS":   "Energy",
    "ADANIPOWER.NS":  "Energy",

    # FMCG / consumer staples
    "HINDUNILVR.NS":  "FMCG",
    "ITC.NS":         "FMCG",
    "NESTLEIND.NS":   "FMCG",
    "BRITANNIA.NS":   "FMCG",
    "DABUR.NS":       "FMCG",
    "GODREJCP.NS":    "FMCG",
    "TATACONSUM.NS":  "FMCG",

    # Auto
    "MARUTI.NS":      "Auto",
    "TATAMOTORS.NS":  "Auto",
    "M&M.NS":         "Auto",
    "BAJAJ-AUTO.NS":  "Auto",
    "EICHERMOT.NS":   "Auto",
    "HEROMOTOCO.NS":  "Auto",

    # Pharma / healthcare
    "SUNPHARMA.NS":   "Pharma",
    "DRREDDY.NS":     "Pharma",
    "CIPLA.NS":       "Pharma",
    "DIVISLAB.NS":    "Pharma",
    "APOLLOHOSP.NS":  "Pharma",

    # Metals & materials
    "TATASTEEL.NS":   "Metals",
    "JSWSTEEL.NS":    "Metals",
    "HINDALCO.NS":    "Metals",
    "VEDL.NS":        "Metals",
    "ADANIENT.NS":    "Metals",

    # Telecom
    "BHARTIARTL.NS":  "Telecom",

    # Construction & cement
    "LT.NS":          "Construction",
    "ULTRACEMCO.NS":  "Construction",
    "GRASIM.NS":      "Construction",
    "SHREECEM.NS":    "Construction",
    "ADANIPORTS.NS":  "Construction",

    # Consumer discretionary
    "TITAN.NS":       "Consumer",
    "ASIANPAINT.NS":  "Consumer",
    "NYKAA.NS":       "Consumer",
    "DMART.NS":       "Consumer",

    # ETFs
    "NIFTYBEES.NS":   "ETF",
    "JUNIORBEES.NS":  "ETF",
    "BANKBEES.NS":    "ETF",
}


def sector_for(symbol: str) -> str:
    """Return the sector for a symbol, or 'Other' if unknown.
    'Other' is a real bucket — the sector cap still applies to it, so
    unknown symbols can't sneak past the limit."""
    return NSE_SECTOR_MAP.get(symbol, "Other")


def build_sector_notional(positions_notional: dict[str, float]) -> dict[str, float]:
    """Aggregate per-symbol notional into per-sector notional. Uses absolute
    value because the sector cap is on gross exposure."""
    out: dict[str, float] = {}
    for sym, notional in positions_notional.items():
        s = sector_for(sym)
        out[s] = out.get(s, 0.0) + abs(notional)
    return out


def build_symbol_to_sector(symbols: list[str]) -> dict[str, str]:
    """Per-symbol map for the universe. Used by PortfolioState."""
    return {s: sector_for(s) for s in symbols}
