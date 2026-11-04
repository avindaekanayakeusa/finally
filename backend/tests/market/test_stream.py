"""Tests for the SSE stream (generator driven directly, no server needed)."""

import asyncio
import json

from app.market.cache import PriceCache
from app.market.stream import SSE_HEADERS, create_stream_router, generate_price_events


class FakeRequest:
    """Reports connected for N polls, then disconnected."""

    def __init__(self, polls_before_disconnect: int, host: str | None = None):
        self._n = polls_before_disconnect
        self.client = type("Client", (), {"host": host})() if host else None

    async def is_disconnected(self) -> bool:
        self._n -= 1
        return self._n < 0


async def collect(cache, polls, **kw):
    return [f async for f in generate_price_events(cache, FakeRequest(polls), interval=0, **kw)]


def data_frames(frames):
    return [json.loads(f.removeprefix("data: ")) for f in frames if f.startswith("data: ")]


async def test_first_frame_is_retry_then_data():
    c = PriceCache()
    c.update("AAPL", 190.0, session_open=189.0)
    frames = await collect(c, polls=1)
    assert frames[0] == "retry: 1000\n\n"
    assert frames[1].startswith("data: ") and frames[1].endswith("\n\n")
    body = data_frames(frames)[0]
    assert body["AAPL"]["price"] == 190.0
    assert body["AAPL"]["direction"] == "flat"
    assert body["AAPL"]["session_open"] == 189.0


async def test_frame_contains_all_tickers_with_full_contract():
    c = PriceCache()
    c.update("AAPL", 190.0)
    c.update("MSFT", 420.0)
    body = data_frames(await collect(c, polls=1))[0]
    assert set(body) == {"AAPL", "MSFT"}
    assert set(body["MSFT"]) == {
        "ticker", "price", "previous_price", "timestamp", "change", "change_percent",
        "direction", "session_open", "day_change", "day_change_percent",
    }


async def test_empty_cache_sends_empty_object_once():
    frames = await collect(PriceCache(), polls=3, heartbeat=999)
    assert data_frames(frames) == [{}]


async def test_no_duplicate_frames_without_changes():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=5, heartbeat=999)
    assert len(data_frames(frames)) == 1


async def test_new_frame_on_change():
    c = PriceCache()
    c.update("AAPL", 190.0)

    class MutatingRequest(FakeRequest):
        async def is_disconnected(self):
            if self._n == 1:
                c.update("AAPL", 191.0)
            return await super().is_disconnected()

    frames = [f async for f in generate_price_events(c, MutatingRequest(2), interval=0, heartbeat=999)]
    bodies = data_frames(frames)
    assert [b["AAPL"]["price"] for b in bodies] == [190.0, 191.0]
    assert bodies[1]["AAPL"]["direction"] == "up"


async def test_removed_ticker_disappears_from_next_frame():
    c = PriceCache()
    c.update("AAPL", 190.0)
    c.update("MSFT", 420.0)

    class RemovingRequest(FakeRequest):
        async def is_disconnected(self):
            if self._n == 1:
                c.remove("MSFT")
            return await super().is_disconnected()

    frames = [f async for f in generate_price_events(c, RemovingRequest(2), interval=0, heartbeat=999)]
    assert [set(b) for b in data_frames(frames)] == [{"AAPL", "MSFT"}, {"AAPL"}]


async def test_heartbeat_when_idle():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=3, heartbeat=0)
    assert ": ping\n\n" in frames
    assert len(data_frames(frames)) == 1


async def test_no_heartbeat_before_interval():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=3, heartbeat=999)
    assert ": ping\n\n" not in frames


async def test_stops_immediately_if_already_disconnected():
    frames = await collect(PriceCache(), polls=0)
    assert frames == ["retry: 1000\n\n"]


async def test_cancellation_ends_generator_cleanly():
    c = PriceCache()
    gen = generate_price_events(c, FakeRequest(10**9, host="1.2.3.4"), interval=10)
    assert await gen.__anext__() == "retry: 1000\n\n"
    await gen.__anext__()  # data frame; generator now sleeping on the next anext
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration):
        pass


def test_router_factory_is_reentrant():
    r1, r2 = create_stream_router(PriceCache()), create_stream_router(PriceCache())
    assert len(r1.routes) == len(r2.routes) == 1
    assert r1.routes[0].path == "/api/stream/prices"


async def test_endpoint_returns_event_stream_response():
    """Call the route handler directly; TestClient can't end an infinite stream."""
    c = PriceCache()
    c.update("AAPL", 190.0)
    router = create_stream_router(c, interval=0)
    handler = router.routes[0].endpoint
    resp = await handler(FakeRequest(1))
    assert resp.media_type == "text/event-stream"
    for key, value in SSE_HEADERS.items():
        assert resp.headers[key.lower()] == value
    frames = [f async for f in resp.body_iterator]
    assert frames[0] == "retry: 1000\n\n"
    assert data_frames(frames)[0]["AAPL"]["price"] == 190.0
