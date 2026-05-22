"""Value-at-Risk and Conditional VaR."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def var_historical(returns: pd.Series, alpha: float = 0.99) -> float:
    """Historical VaR at confidence `alpha`. Returns a positive loss number."""
    if returns.empty:
        return 0.0
    q = returns.quantile(1.0 - alpha)
    return float(-q) if q < 0 else 0.0


def cvar_historical(returns: pd.Series, alpha: float = 0.99) -> float:
    """Conditional VaR (Expected Shortfall): mean of returns worse than VaR."""
    if returns.empty:
        return 0.0
    q = returns.quantile(1.0 - alpha)
    tail = returns[returns <= q]
    if tail.empty:
        return 0.0
    return float(-tail.mean())


def var_parametric(returns: pd.Series, alpha: float = 0.99) -> float:
    """Variance-covariance VaR assuming normal returns. Sanity-check only."""
    if returns.empty:
        return 0.0
    mu = returns.mean()
    sigma = returns.std()
    if sigma == 0 or np.isnan(sigma):
        return 0.0
    z = stats.norm.ppf(1.0 - alpha)
    var = -(mu + z * sigma)
    return float(max(var, 0.0))


def portfolio_var(
    weights: pd.Series,
    returns_matrix: pd.DataFrame,
    alpha: float = 0.99,
    method: str = "historical",
) -> float:
    """VaR of a portfolio with weights `w` over returns matrix `returns_matrix`.

    weights: index = symbol, values = portfolio weights (sum can be anything).
    returns_matrix: rows = time, columns = symbol, values = returns.
    """
    aligned = returns_matrix.reindex(columns=weights.index).dropna(how="all")
    port_rets = (aligned * weights).sum(axis=1)
    if method == "parametric":
        return var_parametric(port_rets, alpha)
    return var_historical(port_rets, alpha)
