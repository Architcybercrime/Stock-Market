"""WebSocket route for streaming market ticks to the dashboard.

Phase 1: emits stub ticks every second so the dashboard can verify wiring.
Phase 2: subscribes to the ingestion bus (Kafka/Redis Pub-Sub) and forwards
real ticks.

Auth: querystring `?token=...` because browser WebSocket cannot send headers.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from libs.common.config import settings
from libs.common.logging import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["ws"])


def _verify_ws_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/ticks")
async def ws_ticks(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    symbol: str = Query(default="AAPL"),
) -> None:
    user = _verify_ws_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    log.info("ws.connect", user=user, symbol=symbol)
    try:
        # Stub stream: random walk around 100. Replace with Redis pub-sub bridge.
        price = 100.0
        while True:
            price *= 1.0 + random.uniform(-0.002, 0.002)
            msg = {
                "symbol": symbol,
                "ts": datetime.now(UTC).isoformat(),
                "price": round(price, 4),
                "source": "stub",
            }
            await websocket.send_text(json.dumps(msg))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        log.info("ws.disconnect", user=user, symbol=symbol)
