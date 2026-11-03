"""Market data subsystem for FinAlly.

Public API:
    PriceUpdate               - Immutable price snapshot
    PriceCache                - Thread-safe in-memory price store
    MarketDataSource          - Abstract interface for data providers
    create_market_data_source - Factory: simulator or Massive, from env
    create_stream_router      - FastAPI router for the SSE endpoint
    normalize_ticker          - Canonical ticker formatting / validation
"""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate, normalize_ticker
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
    "normalize_ticker",
]
