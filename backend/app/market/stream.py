"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx etc.)
}


def create_stream_router(
    price_cache: PriceCache,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> APIRouter:
    """Build a fresh router exposing ``GET /api/stream/prices``.

    A new APIRouter is created per call, so calling this more than once never
    registers duplicate routes.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """Stream full price snapshots (object keyed by ticker) as SSE frames."""
        return StreamingResponse(
            generate_price_events(price_cache, request, interval, heartbeat),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return router


async def generate_price_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames until the client disconnects.

    - First frame: ``retry: 1000`` (browser reconnects 1s after a drop).
    - A ``data:`` frame with the full snapshot whenever the cache version
      changes (checked every ``interval`` seconds). An empty cache sends
      ``data: {}`` once.
    - A ``: ping`` comment after ``heartbeat`` seconds without data.
    """
    client = request.client.host if request.client else "unknown"
    logger.info("SSE connected: %s", client)
    yield "retry: 1000\n\n"

    last_version = -1
    last_sent = time.monotonic()
    try:
        while not await request.is_disconnected():
            version, prices = price_cache.snapshot()
            now = time.monotonic()
            if version != last_version:
                last_version = version
                payload = {t: u.to_dict() for t, u in prices.items()}
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                last_sent = now
            elif now - last_sent >= heartbeat:
                yield ": ping\n\n"
                last_sent = now
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("SSE disconnected: %s", client)
