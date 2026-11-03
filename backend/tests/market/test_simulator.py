"""Tests for GBMSimulator."""

from unittest.mock import patch

import numpy as np

from app.market.seed_prices import SEED_PRICES, UNKNOWN_SEED_RANGE
from app.market.simulator import GBMSimulator


class TestGBMSimulator:
    """Unit tests for the GBM price simulator."""

    def test_step_returns_all_tickers(self):
        """Test that step() returns prices for all tickers."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        result = sim.step()
        assert set(result.keys()) == {"AAPL", "GOOGL"}

    def test_prices_are_positive(self):
        """GBM prices can never go negative (exp() is always positive)."""
        sim = GBMSimulator(tickers=["AAPL"])
        for _ in range(10_000):
            prices = sim.step()
            assert prices["AAPL"] > 0

    def test_initial_prices_match_seeds(self):
        """Test that initial prices match seed prices."""
        sim = GBMSimulator(tickers=["AAPL"])
        # Before any step, price should be the seed price
        assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]

    def test_add_ticker(self):
        """Test adding a ticker dynamically."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("TSLA")
        result = sim.step()
        assert "TSLA" in result

    def test_remove_ticker(self):
        """Test removing a ticker."""
        sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
        sim.remove_ticker("GOOGL")
        result = sim.step()
        assert "GOOGL" not in result
        assert "AAPL" in result

    def test_add_duplicate_is_noop(self):
        """Test that adding a duplicate ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.add_ticker("AAPL")
        assert len(sim._tickers) == 1

    def test_remove_nonexistent_is_noop(self):
        """Test that removing a non-existent ticker is a no-op."""
        sim = GBMSimulator(tickers=["AAPL"])
        sim.remove_ticker("NOPE")  # Should not raise

    def test_unknown_ticker_gets_random_seed_price(self):
        """Test that unknown tickers get random seed prices."""
        sim = GBMSimulator(tickers=["ZZZZ"])
        price = sim.get_price("ZZZZ")
        assert price is not None
        assert 50.0 <= price <= 300.0

    def test_empty_step(self):
        """Test stepping with no tickers."""
        sim = GBMSimulator(tickers=[])
        result = sim.step()
        assert result == {}

    def test_prices_change_over_time(self):
        """After many steps, prices should have drifted from their seeds."""
        sim = GBMSimulator(tickers=["AAPL"])
        initial_price = sim.get_price("AAPL")

        for _ in range(1000):
            sim.step()

        final_price = sim.get_price("AAPL")
        # Price should have changed (extremely unlikely to be exactly the seed)
        assert final_price != initial_price

    def test_cholesky_rebuilds_on_add(self):
        """Test that Cholesky matrix is rebuilt when tickers are added."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None  # Only 1 ticker, no correlation matrix
        sim.add_ticker("GOOGL")
        assert sim._cholesky is not None  # Now 2 tickers, matrix exists

    def test_cholesky_none_with_one_ticker(self):
        """Test that Cholesky is None with only one ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim._cholesky is None

    def test_get_price_returns_none_for_unknown(self):
        """Test that get_price returns None for unknown ticker."""
        sim = GBMSimulator(tickers=["AAPL"])
        assert sim.get_price("UNKNOWN") is None

    def test_pairwise_correlation_tech_stocks(self):
        """Test that tech stocks have high correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "GOOGL")
        assert corr == 0.6

    def test_pairwise_correlation_finance_stocks(self):
        """Test that finance stocks have moderate correlation."""
        corr = GBMSimulator._pairwise_correlation("JPM", "V")
        assert corr == 0.5

    def test_pairwise_correlation_tsla(self):
        """Test that TSLA has lower correlation with everything."""
        corr = GBMSimulator._pairwise_correlation("TSLA", "AAPL")
        assert corr == 0.3
        corr = GBMSimulator._pairwise_correlation("TSLA", "JPM")
        assert corr == 0.3

    def test_pairwise_correlation_cross_sector(self):
        """Test cross-sector correlation."""
        corr = GBMSimulator._pairwise_correlation("AAPL", "JPM")
        assert corr == 0.3

    def test_default_dt_is_reasonable(self):
        """Test that default dt is a reasonable small value."""
        assert 0 < GBMSimulator.DEFAULT_DT < 0.0001

    def test_prices_rounded_to_two_decimals(self):
        """Test that prices are rounded to 2 decimal places."""
        sim = GBMSimulator(tickers=["AAPL"])
        result = sim.step()
        price_str = str(result["AAPL"])
        # Check that we have at most 2 decimal places
        if '.' in price_str:
            decimal_part = price_str.split('.')[1]
            assert len(decimal_part) <= 2


class TestGBMSimulatorV2:
    """Behaviour added in design v2."""

    DEFAULTS = list(SEED_PRICES)

    def test_deterministic_with_seeded_rng(self):
        a = GBMSimulator(self.DEFAULTS + ["ZZZ"], rng=np.random.default_rng(1))
        b = GBMSimulator(self.DEFAULTS + ["ZZZ"], rng=np.random.default_rng(1))
        assert [a.step() for _ in range(50)] == [b.step() for _ in range(50)]

    def test_unknown_seed_in_range(self):
        sim = GBMSimulator(["ZZZ"], rng=np.random.default_rng(3))
        lo, hi = UNKNOWN_SEED_RANGE
        assert lo <= sim.get_price("ZZZ") <= hi

    def test_cholesky_ok_for_defaults_plus_many_unknowns(self):
        sim = GBMSimulator(self.DEFAULTS + [f"X{i}" for i in range(40)])
        assert sim._cholesky is not None
        assert sim._cholesky.shape == (50, 50)

    def test_cholesky_failure_falls_back_to_independent(self):
        with patch(
            "app.market.simulator.np.linalg.cholesky", side_effect=np.linalg.LinAlgError("bad")
        ):
            sim = GBMSimulator(["AAPL", "MSFT"])
        assert sim._cholesky is None
        assert set(sim.step()) == {"AAPL", "MSFT"}

    def test_empirical_correlation_tech_vs_finance(self):
        sim = GBMSimulator(["AAPL", "MSFT", "JPM"], event_probability=0, rng=np.random.default_rng(0))
        prev = {t: sim.get_price(t) for t in sim.get_tickers()}
        rets = {t: [] for t in prev}
        for _ in range(20_000):
            sim.step()
            for t in prev:
                p = sim.get_price(t)
                rets[t].append(np.log(p / prev[t]))
                prev[t] = p
        tech = np.corrcoef(rets["AAPL"], rets["MSFT"])[0, 1]
        cross = np.corrcoef(rets["AAPL"], rets["JPM"])[0, 1]
        assert 0.55 < tech < 0.65
        assert 0.25 < cross < 0.35

    def test_shock_events_fire_with_probability_one(self):
        sim = GBMSimulator(["AAPL"], event_probability=1.0, rng=np.random.default_rng(5))
        before = sim.get_price("AAPL")
        sim.step()
        move = abs(sim.get_price("AAPL") / before - 1)
        assert 0.019 < move < 0.051

    def test_session_open_is_seed(self):
        sim = GBMSimulator(["AAPL"])
        sim.step()
        assert sim.get_session_open("AAPL") == SEED_PRICES["AAPL"]

    def test_session_open_removed_with_ticker(self):
        sim = GBMSimulator(["AAPL", "MSFT"])
        sim.remove_ticker("AAPL")
        assert sim.get_session_open("AAPL") is None

    def test_ticker_params_not_shared(self):
        sim = GBMSimulator(["AAPL"])
        sim._params["AAPL"]["sigma"] = 9.9
        assert GBMSimulator(["AAPL"])._params["AAPL"]["sigma"] != 9.9
