"""Integration tests for SimulatorDataSource."""

import asyncio
from unittest.mock import patch

import numpy as np
import pytest

from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES
from app.market.simulator import SimulatorDataSource


@pytest.mark.asyncio
class TestSimulatorDataSource:
    """Integration tests for the SimulatorDataSource."""

    async def test_start_populates_cache(self):
        """Test that start() immediately populates the cache."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        # Cache should have seed prices immediately (before first loop tick)
        assert cache.get("AAPL") is not None
        assert cache.get("GOOGL") is not None

        await source.stop()

    async def test_prices_update_over_time(self):
        """Test that prices are updated periodically."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
        await source.start(["AAPL"])

        initial_version = cache.version
        await asyncio.sleep(0.3)  # Several update cycles

        # Version should have incremented (prices updated)
        assert cache.version > initial_version

        await source.stop()

    async def test_stop_is_clean(self):
        """Test that stop() is clean and idempotent."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL"])
        await source.stop()
        # Double stop should not raise
        await source.stop()

    async def test_add_ticker(self):
        """Test adding a ticker dynamically."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL"])

        await source.add_ticker("TSLA")
        assert "TSLA" in source.get_tickers()
        assert cache.get("TSLA") is not None

        await source.stop()

    async def test_remove_ticker(self):
        """Test removing a ticker."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "TSLA"])

        await source.remove_ticker("TSLA")
        assert "TSLA" not in source.get_tickers()
        assert cache.get("TSLA") is None

        await source.stop()

    async def test_get_tickers(self):
        """Test getting the list of active tickers."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        tickers = source.get_tickers()
        assert set(tickers) == {"AAPL", "GOOGL"}

        await source.stop()

    async def test_empty_start(self):
        """Test starting with no tickers."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start([])

        assert len(cache) == 0
        assert source.get_tickers() == []

        await source.stop()

    async def test_exception_resilience(self):
        """Test that simulator continues running after errors."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)

        # Start with a valid ticker
        await source.start(["AAPL"])

        # Wait for some updates
        await asyncio.sleep(0.15)

        # Task should still be running
        assert source._task is not None
        assert not source._task.done()

        await source.stop()

    async def test_custom_update_interval(self):
        """Test using a custom update interval."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.01)
        await source.start(["AAPL"])

        initial_version = cache.version
        await asyncio.sleep(0.05)  # Should get ~5 updates

        # Should have multiple updates with fast interval
        assert cache.version > initial_version + 2

        await source.stop()

    async def test_custom_event_probability(self):
        """Test creating source with custom event probability."""
        cache = PriceCache()
        # Very high event probability for testing
        source = SimulatorDataSource(
            price_cache=cache, update_interval=0.1, event_probability=1.0
        )
        await source.start(["AAPL"])

        # Just verify it starts and stops cleanly
        await asyncio.sleep(0.2)
        await source.stop()


@pytest.mark.asyncio
class TestSimulatorDataSourceV2:
    """Normalization, session_open, determinism, real error resilience."""

    async def test_add_ticker_normalizes(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=10)
        await source.start(["AAPL"])
        await source.add_ticker(" pypl ")
        assert "PYPL" in source.get_tickers()
        assert "PYPL" in cache
        assert " pypl " not in source.get_tickers()
        await source.stop()

    async def test_start_normalizes_and_dedupes(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=10)
        await source.start(["aapl", "AAPL", " msft"])
        assert source.get_tickers() == ["AAPL", "MSFT"]
        assert set(cache.get_all()) == {"AAPL", "MSFT"}
        await source.stop()

    async def test_start_rejects_invalid_ticker(self):
        source = SimulatorDataSource(price_cache=PriceCache())
        with pytest.raises(ValueError):
            await source.start(["AAPL", "$$$"])

    async def test_remove_ticker_normalizes(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=10)
        await source.start(["AAPL", "TSLA"])
        await source.remove_ticker("tsla")
        assert source.get_tickers() == ["AAPL"]
        assert "TSLA" not in cache
        await source.stop()

    async def test_add_duplicate_does_not_reseed(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=10)
        await source.start(["AAPL"])
        v = cache.version
        await source.add_ticker("aapl")
        assert cache.version == v
        await source.stop()

    async def test_seeded_cache_has_session_open(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=10)
        await source.start(["AAPL"])
        u = cache.get("AAPL")
        assert u.price == SEED_PRICES["AAPL"]
        assert u.session_open == SEED_PRICES["AAPL"]
        assert u.day_change == 0.0
        await source.stop()

    async def test_session_open_survives_ticks(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.01)
        await source.start(["AAPL"])
        await source.add_ticker("PYPL")
        await asyncio.sleep(0.05)
        await source.stop()
        assert cache.get("AAPL").session_open == SEED_PRICES["AAPL"]
        assert cache.get("PYPL").session_open is not None
        assert cache.get("AAPL").day_change_percent is not None

    async def test_injected_rng_is_deterministic(self):
        caches = []
        for _ in range(2):
            cache = PriceCache()
            source = SimulatorDataSource(
                price_cache=cache, update_interval=10, rng=np.random.default_rng(11)
            )
            await source.start(["AAPL", "ZZZZ"])
            await source.stop()
            caches.append({t: u.price for t, u in cache.get_all().items()})
        assert caches[0] == caches[1]

    async def test_loop_survives_step_exception(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.01)
        await source.start(["AAPL"])
        real_step = source._sim.step
        calls = {"n": 0}

        def flaky_step():
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("boom")
            return real_step()

        v = cache.version
        with patch.object(source._sim, "step", side_effect=flaky_step):
            await asyncio.sleep(0.1)
        assert calls["n"] > 2
        assert not source._task.done()
        assert cache.version > v  # kept updating after the failures
        await source.stop()

    async def test_no_writes_after_stop(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.01)
        await source.start(["AAPL"])
        await source.stop()
        v = cache.version
        await asyncio.sleep(0.05)
        assert cache.version == v

    async def test_methods_before_start_are_safe(self):
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache)
        assert source.get_tickers() == []
        await source.add_ticker("AAPL")  # no simulator yet: no-op
        await source.remove_ticker("AAPL")
        await source.stop()
        assert len(cache) == 0
