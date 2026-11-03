"""Tests for the SSE stream generator and router factory (no server needed)."""

import json

from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache
from app.market.stream import SSE_HEADERS, create_stream_router, generate_price_events


class FakeRequest:
    """Reports connected for `polls` checks, then disconnected."""

    def __init__(self, polls: int, on_poll=None):
        self._n = polls
        self._on_poll = on_poll
        self.client = None

    async def is_disconnected(self) -> bool:
        if self._on_poll:
            self._on_poll(self._n)
        self._n -= 1
        return self._n < 0


async def collect(cache, polls, on_poll=None, **kw):
    req = FakeRequest(polls, on_poll)
    return [f async for f in generate_price_events(cache, req, interval=0, **kw)]


def data_frames(frames):
    return [json.loads(f.removeprefix("data: ")) for f in frames if f.startswith("data: ")]


async def test_first_frame_is_retry_then_data():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=1)
    assert frames[0] == "retry: 1000\n\n"
    body = data_frames(frames)[0]
    assert body["AAPL"]["price"] == 190.0
    assert body["AAPL"]["direction"] == "flat"
    assert frames[1].endswith("\n\n")


async def test_empty_cache_sends_empty_object_once():
    frames = await collect(PriceCache(), polls=3, heartbeat=999)
    assert data_frames(frames) == [{}]


async def test_no_duplicate_frames_without_changes():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=5, heartbeat=999)
    assert len(data_frames(frames)) == 1


async def test_new_frame_on_each_change_and_removal():
    c = PriceCache()
    c.update("AAPL", 190.0)
    c.update("MSFT", 420.0)

    def mutate(n):
        if n == 2:
            c.update("AAPL", 191.0)
        elif n == 1:
            c.remove("MSFT")

    frames = data_frames(await collect(c, polls=3, on_poll=mutate, heartbeat=999))
    assert len(frames) == 3
    assert frames[1]["AAPL"]["direction"] == "up"
    assert "MSFT" not in frames[2]


async def test_heartbeat_when_idle():
    c = PriceCache()
    c.update("AAPL", 190.0)
    frames = await collect(c, polls=3, heartbeat=0)
    assert ": ping\n\n" in frames


async def test_stops_immediately_when_disconnected():
    frames = await collect(PriceCache(), polls=0)
    assert frames == ["retry: 1000\n\n"]


def test_router_factory_is_reentrant():
    r1, r2 = create_stream_router(PriceCache()), create_stream_router(PriceCache())
    assert len(r1.routes) == len(r2.routes) == 1
    assert r1.routes[0].path == "/api/stream/prices"


async def test_endpoint_returns_event_stream_response():
    """Call the route's endpoint directly and consume the response body."""
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    router = create_stream_router(cache, interval=0)
    endpoint = router.routes[0].endpoint
    resp = await endpoint(FakeRequest(polls=1))
    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "text/event-stream"
    for k, v in SSE_HEADERS.items():
        assert resp.headers[k] == v
    frames = [f async for f in resp.body_iterator]
    assert "AAPL" in data_frames(frames)[0]
