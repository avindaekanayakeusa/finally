"""Tests for PriceCache."""

import threading
from unittest.mock import patch

from app.market.cache import PriceCache


class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    def test_first_update_is_flat(self):
        """Test that the first update has flat direction."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.direction == "flat"
        assert update.previous_price == 190.50

    def test_direction_up(self):
        """Test price update with upward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 191.00)
        assert update.direction == "up"
        assert update.change == 1.00

    def test_direction_down(self):
        """Test price update with downward direction."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        update = cache.update("AAPL", 189.00)
        assert update.direction == "down"
        assert update.change == -1.00

    def test_remove(self):
        """Test removing a ticker from cache."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.remove("AAPL")
        assert cache.get("AAPL") is None

    def test_remove_nonexistent(self):
        """Test removing a ticker that doesn't exist."""
        cache = PriceCache()
        cache.remove("AAPL")  # Should not raise

    def test_get_all(self):
        """Test getting all prices."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        all_prices = cache.get_all()
        assert set(all_prices.keys()) == {"AAPL", "GOOGL"}

    def test_version_increments(self):
        """Test that version counter increments."""
        cache = PriceCache()
        v0 = cache.version
        cache.update("AAPL", 190.00)
        assert cache.version == v0 + 1
        cache.update("AAPL", 191.00)
        assert cache.version == v0 + 2

    def test_get_price_convenience(self):
        """Test the convenience get_price method."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("NOPE") is None

    def test_len(self):
        """Test __len__ method."""
        cache = PriceCache()
        assert len(cache) == 0
        cache.update("AAPL", 190.00)
        assert len(cache) == 1
        cache.update("GOOGL", 175.00)
        assert len(cache) == 2

    def test_contains(self):
        """Test __contains__ method."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        assert "AAPL" in cache
        assert "GOOGL" not in cache

    def test_custom_timestamp(self):
        """Test updating with a custom timestamp."""
        cache = PriceCache()
        custom_ts = 1234567890.0
        update = cache.update("AAPL", 190.50, timestamp=custom_ts)
        assert update.timestamp == custom_ts

    def test_price_rounding(self):
        """Test that prices are rounded to 2 decimal places."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.12345)
        assert update.price == 190.12


class TestPriceCacheV2:
    """session_open, snapshot(), version semantics, thread safety."""

    def test_timestamp_zero_is_respected(self):
        assert PriceCache().update("AAPL", 1.0, timestamp=0.0).timestamp == 0.0

    def test_default_timestamp_is_now(self):
        with patch("app.market.cache.time.time", return_value=123.0):
            assert PriceCache().update("AAPL", 1.0).timestamp == 123.0

    def test_remove_bumps_version_only_when_present(self):
        c = PriceCache()
        c.update("AAPL", 1.0)
        v = c.version
        c.remove("AAPL")
        assert c.version == v + 1
        c.remove("AAPL")
        assert c.version == v + 1  # no-op remove doesn't bump

    def test_session_open_stored_and_rounded(self):
        u = PriceCache().update("AAPL", 190.0, session_open=189.004)
        assert u.session_open == 189.0

    def test_session_open_carried_forward(self):
        c = PriceCache()
        c.update("AAPL", 190.0, session_open=189.0)
        assert c.update("AAPL", 191.0).session_open == 189.0

    def test_session_open_can_be_replaced(self):
        c = PriceCache()
        c.update("AAPL", 190.0, session_open=189.0)
        assert c.update("AAPL", 191.0, session_open=190.5).session_open == 190.5

    def test_session_open_defaults_to_none(self):
        assert PriceCache().update("AAPL", 190.0).session_open is None

    def test_snapshot_returns_version_and_copy(self):
        c = PriceCache()
        c.update("AAPL", 190.0)
        c.update("MSFT", 420.0)
        version, prices = c.snapshot()
        assert version == 2
        assert set(prices) == {"AAPL", "MSFT"}
        prices.clear()
        assert len(c) == 2

    def test_get_all_returns_copy(self):
        c = PriceCache()
        c.update("AAPL", 190.0)
        c.get_all().clear()
        assert "AAPL" in c

    def test_concurrent_writers(self):
        c = PriceCache()

        def write():
            for i in range(1000):
                c.update("AAPL", float(i + 1))

        threads = [threading.Thread(target=write) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.version == 8000
