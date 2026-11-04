"""Fixtures for chat tests: fake market source and a TestClient app."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import create_chat_router
from app.db import DEFAULT_TICKERS
from app.market import MarketDataSource, PriceCache

PRICE = 100.0


class FakeSource(MarketDataSource):
    """Tracks tickers and prices each one at PRICE as soon as it is added."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self.tickers: list[str] = []

    async def start(self, tickers: list[str]) -> None:
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self.tickers:
            self.tickers.append(ticker)
            self.cache.update(ticker, PRICE)

    async def remove_ticker(self, ticker: str) -> None:
        self.tickers = [t for t in self.tickers if t != ticker]
        self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)


@pytest.fixture
def cache():
    return PriceCache()


@pytest.fixture
def source(cache):
    src = FakeSource(cache)
    for t in DEFAULT_TICKERS:
        src.tickers.append(t)
        cache.update(t, PRICE)
    return src


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def client(db_conn, cache, source):
    """App with only the chat router, sharing the temp database from db_conn."""
    app = FastAPI()
    app.include_router(create_chat_router(cache, source))
    return TestClient(app)
