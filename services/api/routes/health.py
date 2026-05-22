"""Health and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

from libs.common.config import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe. Always returns OK if the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness probe. Reports whether the app is ready to serve traffic.

    Production should check Postgres, Redis, and broker connectivity here.
    """
    return {
        "status": "ready",
        "env": settings.app_env,
        "trading_mode": settings.trading_mode,
        "live_trading_enabled": settings.live_trading_enabled,
    }
