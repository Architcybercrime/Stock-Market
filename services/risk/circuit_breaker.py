"""Circuit breakers: daily loss and drawdown triggers.

When tripped, the breaker blocks all new orders until manually reset by an
operator. The state is in-memory by default; production should persist it to
Redis or Postgres so it survives restarts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from libs.common.logging import get_logger

log = get_logger(__name__)


class CircuitBreakerState(str, enum.Enum):
    OK = "ok"
    DAILY_LOSS_TRIPPED = "daily_loss_tripped"
    DRAWDOWN_TRIPPED = "drawdown_tripped"


@dataclass
class CircuitBreaker:
    max_daily_loss_pct: float
    max_drawdown_pct: float
    state: CircuitBreakerState = CircuitBreakerState.OK
    tripped_at: datetime | None = None
    tripped_reason: str = ""
    _peak_equity: float = 0.0
    _start_of_day_equity: float = 0.0
    _current_day: str = ""

    def update(self, equity: float, ts: datetime) -> CircuitBreakerState:
        """Call on every equity update. Returns the current state."""
        # Track peak for drawdown
        if equity > self._peak_equity:
            self._peak_equity = equity
        # Track start-of-day for daily loss
        day_key = ts.date().isoformat()
        if day_key != self._current_day:
            self._current_day = day_key
            self._start_of_day_equity = equity

        # Once tripped, stay tripped until reset.
        if self.state != CircuitBreakerState.OK:
            return self.state

        # Drawdown check
        if self._peak_equity > 0:
            dd = equity / self._peak_equity - 1.0
            if dd <= -self.max_drawdown_pct:
                self._trip(
                    CircuitBreakerState.DRAWDOWN_TRIPPED,
                    f"drawdown {dd:.2%} <= -{self.max_drawdown_pct:.2%}",
                    ts,
                )
                return self.state

        # Daily loss check
        if self._start_of_day_equity > 0:
            daily = equity / self._start_of_day_equity - 1.0
            if daily <= -self.max_daily_loss_pct:
                self._trip(
                    CircuitBreakerState.DAILY_LOSS_TRIPPED,
                    f"daily loss {daily:.2%} <= -{self.max_daily_loss_pct:.2%}",
                    ts,
                )
                return self.state

        return self.state

    def reset(self, actor: str = "operator") -> None:
        prev = self.state
        self.state = CircuitBreakerState.OK
        self.tripped_at = None
        self.tripped_reason = ""
        log.warning("circuit_breaker.reset", actor=actor, previous_state=prev.value)

    def _trip(self, state: CircuitBreakerState, reason: str, ts: datetime) -> None:
        self.state = state
        self.tripped_at = ts or datetime.now(UTC)
        self.tripped_reason = reason
        log.critical("circuit_breaker.tripped", state=state.value, reason=reason)
