"""FastAPI entry point.

Routes are grouped under /api/v1. Health endpoints sit at root for k8s probes.
Prometheus exposition at /metrics.

This is the production surface. Anything that mutates state (kill switch, live
trading toggles) requires an operator role.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from libs.common.config import settings
from libs.common.logging import configure_logging, get_logger
from services.api.routes import auth as auth_routes
from services.api.routes import health, portfolio, risk, signals, ws

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, json_logs=(settings.app_env != "development"))
    log.info("api.startup", env=settings.app_env, trading_mode=settings.trading_mode)
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="Stock_Market Trading Platform API",
    version="0.1.0",
    description=(
        "Institutional trading platform. Read-only by default. Mutating "
        "endpoints (kill switch, live trading) require operator role."
    ),
    lifespan=lifespan,
)

# Allow the local Next.js dev server. Tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoints at root so k8s probes don't need versioning.
app.include_router(health.router)

# Versioned routes
app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(risk.router, prefix="/api/v1")
app.include_router(ws.router, prefix="/api/v1")


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus exposition endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
