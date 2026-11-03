"""Tests for market data source factory."""

import os
from unittest.mock import patch

from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource


class TestFactory:
    """Tests for create_market_data_source factory."""

    def test_creates_simulator_when_no_api_key(self):
        """Test that simulator is created when MASSIVE_API_KEY is not set."""
        cache = PriceCache()

        with patch.dict(os.environ, {}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_empty(self):
        """Test that simulator is created when MASSIVE_API_KEY is empty."""
        cache = PriceCache()

        with patch.dict(os.environ, {"MASSIVE_API_KEY": ""}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_simulator_when_api_key_whitespace(self):
        """Test that simulator is created when MASSIVE_API_KEY is whitespace."""
        cache = PriceCache()

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "   "}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)

    def test_creates_massive_when_api_key_set(self):
        """Test that Massive client is created when MASSIVE_API_KEY is set."""
        cache = PriceCache()

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, MassiveDataSource)

    def test_massive_receives_api_key(self):
        """Test that Massive client receives the API key."""
        cache = PriceCache()

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key-123"}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, MassiveDataSource)
        assert source._api_key == "test-key-123"

    def test_simulator_receives_cache(self):
        """Test that simulator receives the cache reference."""
        cache = PriceCache()

        with patch.dict(os.environ, {}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, SimulatorDataSource)
        assert source._cache is cache

    def test_massive_receives_cache(self):
        """Test that Massive client receives the cache reference."""
        cache = PriceCache()

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
            source = create_market_data_source(cache)

        assert isinstance(source, MassiveDataSource)
        assert source._cache is cache


class TestPollIntervalEnv:
    """MASSIVE_POLL_INTERVAL configures the Massive poll cadence."""

    def _source(self, **env):
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "k", **env}, clear=True):
            return create_market_data_source(PriceCache())

    def test_default_interval(self):
        assert self._source()._interval == 15.0

    def test_custom_interval(self):
        assert self._source(MASSIVE_POLL_INTERVAL="5")._interval == 5.0

    def test_interval_clamped_to_minimum(self):
        assert self._source(MASSIVE_POLL_INTERVAL="0.1")._interval == 1.0

    def test_invalid_interval_uses_default(self):
        assert self._source(MASSIVE_POLL_INTERVAL="fast")._interval == 15.0

    def test_blank_interval_uses_default(self):
        assert self._source(MASSIVE_POLL_INTERVAL="  ")._interval == 15.0

    def test_api_key_is_stripped(self):
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "  k  "}, clear=True):
            assert create_market_data_source(PriceCache())._api_key == "k"
