"""Risk endpoints: status, limits, kill switch."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from libs.common.config import settings
from services.api.auth import Role, get_current_user, require_role
from services.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState
from services.risk.kill_switch import KillSwitch
from services.risk.limits import RiskLimitsConfig

router = APIRouter(prefix="/risk", tags=["risk"])


# Module-level singletons. In a long-running worker process these would live
# there; for the API-only scaffold we keep them here so the kill switch state
# survives across requests.
_kill_switch = KillSwitch(Path(settings.data_root) / "KILL_SWITCH")
_breaker = CircuitBreaker(
    max_daily_loss_pct=settings.risk.max_daily_loss_pct,
    max_drawdown_pct=settings.risk.max_drawdown_pct,
)


class RiskStatus(BaseModel):
    kill_switch_engaged: bool
    kill_switch_reason: str
    circuit_breaker_state: str
    circuit_breaker_reason: str
    limits: dict


class KillSwitchAction(BaseModel):
    reason: str


@router.get("/status", response_model=RiskStatus)
async def status(_user=Depends(get_current_user)) -> RiskStatus:
    limits = RiskLimitsConfig(
        max_daily_loss_pct=settings.risk.max_daily_loss_pct,
        max_drawdown_pct=settings.risk.max_drawdown_pct,
        max_position_pct=settings.risk.max_position_pct,
        max_sector_pct=settings.risk.max_sector_pct,
        max_leverage=settings.risk.max_leverage,
        min_cash_buffer_pct=settings.risk.min_cash_buffer_pct,
        max_orders_per_minute=settings.risk.max_orders_per_minute,
        max_order_notional_pct=settings.risk.max_order_notional_pct,
    )
    return RiskStatus(
        kill_switch_engaged=_kill_switch.is_engaged(),
        kill_switch_reason=_kill_switch.reason,
        circuit_breaker_state=_breaker.state.value,
        circuit_breaker_reason=_breaker.tripped_reason,
        limits=limits.__dict__,
    )


@router.post("/kill", response_model=RiskStatus)
async def engage_kill_switch(
    action: KillSwitchAction,
    user=Depends(require_role(Role.OPERATOR)),
) -> RiskStatus:
    _kill_switch.engage(reason=action.reason, actor=user.username)
    return await status(user)


@router.post("/release", response_model=RiskStatus)
async def release_kill_switch(
    user=Depends(require_role(Role.OPERATOR)),
) -> RiskStatus:
    _kill_switch.release(actor=user.username)
    return await status(user)


@router.post("/reset-circuit-breaker", response_model=RiskStatus)
async def reset_breaker(user=Depends(require_role(Role.OPERATOR))) -> RiskStatus:
    _breaker.reset(actor=user.username)
    return await status(user)
