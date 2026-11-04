"""Both data sources conform to the MarketDataSource interface."""

import inspect

import pytest

from app.market import (
    MarketDataSource,
    PriceCache,
    PriceUpdate,
    create_market_data_source,
    create_stream_router,
    normalize_ticker,
)
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource

ABSTRACT = {"start", "stop", "add_ticker", "remove_ticker", "get_tickers"}


def test_interface_is_abstract():
    assert MarketDataSource.__abstractmethods__ == ABSTRACT
    with pytest.raises(TypeError):
        MarketDataSource()


@pytest.mark.parametrize("cls", [SimulatorDataSource, MassiveDataSource])
def test_implementations_conform(cls):
    assert issubclass(cls, MarketDataSource)
    assert not cls.__abstractmethods__
    for name in ABSTRACT - {"get_tickers"}:
        assert inspect.iscoroutinefunction(getattr(cls, name)), name
    assert not inspect.iscoroutinefunction(cls.get_tickers)


def test_public_api_exports():
    import app.market as market

    assert set(market.__all__) == {
        "PriceUpdate",
        "PriceCache",
        "MarketDataSource",
        "create_market_data_source",
        "create_stream_router",
        "normalize_ticker",
    }
    for obj in (PriceUpdate, PriceCache, create_market_data_source, create_stream_router,
                normalize_ticker):
        assert obj is not None
