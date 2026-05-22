"""SignalGenerator: per-strategy per-symbol "should we own this?" score.

This is the daemon's equivalent of the backtester's Strategy — but where the
backtester emits Orders, a SignalGenerator emits StrategySignal objects that
the aggregator combines into orders.

Output convention:
    score in [-1.0, 1.0]
        +1.0 = full long conviction
         0.0 = no opinion
        -1.0 = full short conviction (currently used as "exit if held" since
                we're long-only; aggregator clamps negatives to 0 for sizing)
    confidence in [0.0, 1.0]
        How much trust to put in this score. Aggregator filters by min_confidence.

Each SignalGenerator is *stateless across symbols* but may hold its own model
weights, learned thresholds, etc. The caller passes the symbol's history
in each call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StrategySignal:
    """One strategy's per-symbol opinion at a point in time."""

    strategy: str
    symbol: str
    score: float           # in [-1, 1]
    confidence: float      # in [0, 1]
    rationale: str = ""


class SignalGenerator(ABC):
    """Base for strategy signal generators."""

    name: str = "base"

    @abstractmethod
    def evaluate(self, symbol: str, history: pd.DataFrame) -> StrategySignal:
        """Return a StrategySignal given the symbol's OHLCV history.

        `history` is a DataFrame with at minimum: ts, open, high, low, close, volume.
        Implementations must handle insufficient history gracefully by returning a
        zero-score, low-confidence signal rather than raising.
        """

    def warmup_bars(self) -> int:
        """How many bars of history this signal needs before it's reliable."""
        return 60
