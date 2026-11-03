"""Tests for MassiveDataSource and parse_snapshot.

Snapshots are built with the real SDK model (TickerSnapshot.from_dict) rather
than bare MagicMocks, so attribute names are checked against the actual SDK.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from massive.exceptions import AuthError, BadResponse
from massive.rest.models import TickerSnapshot

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource, parse_snapshot

T_NS = 1_707_580_800_500_000_000  # 2024-02-10T16:00:00.5Z in nanoseconds
T_S = 1_707_580_800.5


def snap(
    ticker,
    price=None,
    t_ns=None,
    prev_close=None,
    minute_close=None,
    day_close=None,
    updated=None,
):
    """Build a real TickerSnapshot from the API's JSON shape."""
    d = {"ticker": ticker}
    if price is not None:
        d["lastTrade"] = {"p": price, **({"t": t_ns} if t_ns else {})}
    if prev_close is not None:
        d["prevDay"] = {"c": prev_close}
    if minute_close is not None:
        d["min"] = {"c": minute_close}
    if day_close is not None:
        d["day"] = {"c": day_close}
    if updated is not None:
        d["updated"] = updated
    return TickerSnapshot.from_dict(d)


def make_source(tickers=("AAPL",), poll_interval=60.0, cache=None):
    """A source with a dummy client, ready for direct _poll_once() calls."""
    source = MassiveDataSource("test-key", cache or PriceCache(), poll_interval=poll_interval)
    source._tickers = list(tickers)
    source._client = MagicMock()
    return source


class TestParseSnapshot:
    """parse_snapshot is pure: test it against real SDK objects."""

    def test_sdk_has_no_last_trade_timestamp(self):
        """Guard: the v1 bug read last_trade.timestamp, which does not exist."""
        s = snap("AAPL", 190.5, t_ns=T_NS)
        assert not hasattr(s.last_trade, "timestamp")
        assert s.last_trade.sip_timestamp == T_NS

    def test_uses_last_trade_and_ns_timestamp(self):
        assert parse_snapshot(snap("AAPL", 190.5, t_ns=T_NS, prev_close=189.0)) == (
            "AAPL",
            190.5,
            T_S,
            189.0,
        )

    def test_falls_back_to_minute_close_and_updated(self):
        parsed = parse_snapshot(snap("MSFT", minute_close=410.0, updated=1_000_000_000_000_000_000))
        assert parsed == ("MSFT", 410.0, 1_000_000_000.0, None)

    def test_falls_back_to_day_close(self):
        ticker, price, _, _ = parse_snapshot(snap("MSFT", day_close=405.0))
        assert (ticker, price) == ("MSFT", 405.0)

    def test_falls_back_to_prev_day_close(self):
        _, price, _, session_open = parse_snapshot(snap("MSFT", prev_close=400.0))
        assert price == 400.0 and session_open == 400.0

    def test_last_trade_preferred_over_fallbacks(self):
        _, price, _, _ = parse_snapshot(
            snap("AAPL", 191.0, minute_close=1.0, day_close=2.0, prev_close=3.0)
        )
        assert price == 191.0

    def test_zero_price_skipped_in_fallback_chain(self):
        _, price, _, _ = parse_snapshot(snap("AAPL", 0.0, minute_close=190.0))
        assert price == 190.0

    def test_missing_timestamps_use_now(self):
        with patch("app.market.massive_client.time.time", return_value=42.0):
            _, _, ts, _ = parse_snapshot(snap("AAPL", 190.0))
        assert ts == 42.0

    def test_returns_none_without_any_price(self):
        assert parse_snapshot(snap("ZZZZ")) is None

    def test_returns_none_without_ticker(self):
        assert parse_snapshot(TickerSnapshot.from_dict({"lastTrade": {"p": 1.0}})) is None

    def test_ticker_uppercased(self):
        assert parse_snapshot(snap("aapl", 190.0))[0] == "AAPL"


@pytest.mark.asyncio
class TestPollOnce:
    async def test_poll_updates_cache(self):
        source = make_source(["AAPL", "GOOGL"])
        snapshots = [snap("AAPL", 190.50, t_ns=T_NS), snap("GOOGL", 175.25, t_ns=T_NS)]
        with patch.object(source, "_fetch_snapshots", return_value=snapshots):
            await source._poll_once()
        assert source._cache.get_price("AAPL") == 190.50
        assert source._cache.get_price("GOOGL") == 175.25

    async def test_timestamp_converted_from_ns(self):
        source = make_source()
        with patch.object(source, "_fetch_snapshots", return_value=[snap("AAPL", 190.5, t_ns=T_NS)]):
            await source._poll_once()
        assert source._cache.get("AAPL").timestamp == T_S

    async def test_writes_session_open(self):
        source = make_source()
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 191.0, t_ns=1, prev_close=190.0)]
        ):
            await source._poll_once()
        u = source._cache.get("AAPL")
        assert u.price == 191.0 and u.session_open == 190.0
        assert u.day_change_percent == 0.5263

    async def test_unusable_snapshot_skipped(self):
        source = make_source(["AAPL", "BAD"])
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 190.5), snap("BAD")]
        ):
            await source._poll_once()
        assert source._cache.get_price("AAPL") == 190.50
        assert "BAD" not in source._cache

    async def test_missing_ticker_logged_not_cached(self, caplog):
        source = make_source(["AAPL", "NOTREAL"])
        with caplog.at_level("INFO", logger="app.market.massive_client"):
            with patch.object(source, "_fetch_snapshots", return_value=[snap("AAPL", 190.0)]):
                await source._poll_once()
        assert "NOTREAL" not in source._cache
        assert "no data for NOTREAL" in caplog.text

    async def test_untracked_ticker_in_response_ignored(self):
        source = make_source(["AAPL"])
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 190.0), snap("MSFT", 410.0)]
        ):
            await source._poll_once()
        assert "MSFT" not in source._cache

    async def test_removed_ticker_not_resurrected_by_inflight_poll(self):
        source = make_source(["AAPL"])

        def fetch(_tickers):
            source._tickers = []  # simulate remove_ticker during the HTTP call
            return [snap("AAPL", 191.0)]

        with patch.object(source, "_fetch_snapshots", side_effect=fetch):
            await source._poll_once()
        assert "AAPL" not in source._cache

    async def test_fetch_receives_ticker_list(self):
        source = make_source(["AAPL", "GOOGL"])
        with patch.object(source, "_fetch_snapshots", return_value=[]) as fetch:
            await source._poll_once()
        fetch.assert_called_once_with(["AAPL", "GOOGL"])

    async def test_only_restricts_tickers(self):
        source = make_source(["AAPL", "GOOGL"])
        with patch.object(source, "_fetch_snapshots", return_value=[]) as fetch:
            await source._poll_once(only=["GOOGL"])
        fetch.assert_called_once_with(["GOOGL"])

    async def test_empty_tickers_skips_poll(self):
        source = make_source([])
        with patch.object(source, "_fetch_snapshots") as fetch:
            await source._poll_once()
        fetch.assert_not_called()

    async def test_no_client_skips_poll(self):
        source = make_source()
        source._client = None
        with patch.object(source, "_fetch_snapshots") as fetch:
            await source._poll_once()
        fetch.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [AuthError("bad key"), BadResponse("429 rate limited"), RuntimeError("network down")],
        ids=["auth", "bad_response", "generic"],
    )
    async def test_api_errors_do_not_crash(self, error):
        source = make_source()
        source._cache.update("AAPL", 189.0)
        with patch.object(source, "_fetch_snapshots", side_effect=error):
            await source._poll_once()  # must not raise
        assert source._cache.get_price("AAPL") == 189.0  # last price kept
        assert source._consecutive_failures == 1

    async def test_backoff_grows_caps_and_resets(self):
        source = make_source(poll_interval=15)
        assert source._next_delay() == 15
        with patch.object(source, "_fetch_snapshots", side_effect=RuntimeError("down")):
            await source._poll_once()
            assert source._next_delay() == 30
            await source._poll_once()
            assert source._next_delay() == 60
            for _ in range(5):
                await source._poll_once()
        assert source._next_delay() == MassiveDataSource.MAX_BACKOFF
        with patch.object(source, "_fetch_snapshots", return_value=[]):
            await source._poll_once()
        assert source._next_delay() == 15


@pytest.mark.asyncio
class TestTickerManagement:
    async def test_add_ticker_polls_immediately(self):
        source = make_source([])
        with patch.object(source, "_fetch_snapshots", return_value=[snap("PYPL", 62.0)]) as fetch:
            await source.add_ticker("PYPL")
        fetch.assert_called_once_with(["PYPL"])
        assert source.get_tickers() == ["PYPL"]
        assert source._cache.get_price("PYPL") == 62.0

    async def test_add_ticker_normalizes(self):
        source = make_source([])
        source._client = None  # skip the immediate poll
        await source.add_ticker("  aapl ")
        assert source.get_tickers() == ["AAPL"]

    async def test_add_duplicate_is_noop(self):
        source = make_source(["AAPL"])
        with patch.object(source, "_fetch_snapshots") as fetch:
            await source.add_ticker("aapl")
        fetch.assert_not_called()
        assert source.get_tickers() == ["AAPL"]

    async def test_add_invalid_ticker_raises(self):
        source = make_source([])
        with pytest.raises(ValueError):
            await source.add_ticker("$$$")

    async def test_remove_ticker(self):
        source = make_source(["AAPL", "GOOGL"])
        source._cache.update("AAPL", 190.0)
        await source.remove_ticker("aapl")
        assert source.get_tickers() == ["GOOGL"]
        assert source._cache.get("AAPL") is None

    async def test_remove_unknown_is_noop(self):
        source = make_source(["AAPL"])
        await source.remove_ticker("MSFT")
        assert source.get_tickers() == ["AAPL"]

    async def test_get_tickers_returns_copy(self):
        source = make_source(["AAPL"])
        source.get_tickers().append("X")
        assert source.get_tickers() == ["AAPL"]


@pytest.mark.asyncio
class TestLifecycle:
    async def test_start_polls_immediately_and_normalizes(self):
        source = MassiveDataSource("test-key", PriceCache(), poll_interval=60.0)
        with patch("app.market.massive_client.RESTClient") as client_cls:
            with patch.object(
                source, "_fetch_snapshots", return_value=[snap("AAPL", 190.5)]
            ) as fetch:
                await source.start(["aapl", "AAPL", "msft"])
        client_cls.assert_called_once_with(api_key="test-key")
        fetch.assert_called_once_with(["AAPL", "MSFT"])
        assert source.get_tickers() == ["AAPL", "MSFT"]
        assert source._cache.get_price("AAPL") == 190.5
        await source.stop()

    async def test_stop_cancels_task(self):
        source = MassiveDataSource("test-key", PriceCache(), poll_interval=10.0)
        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start(["AAPL"])
        task = source._task
        assert task is not None and not task.done()
        await source.stop()
        assert task.cancelled()
        assert source._task is None and source._client is None

    async def test_stop_is_idempotent(self):
        source = MassiveDataSource("test-key", PriceCache())
        await source.stop()
        await source.stop()

    async def test_poll_loop_repeats(self):
        source = MassiveDataSource("test-key", PriceCache(), poll_interval=0.01)
        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]) as fetch:
                await source.start(["AAPL"])
                await asyncio.sleep(0.1)
                await source.stop()
        assert fetch.call_count >= 3

    async def test_fetch_snapshots_calls_sdk(self):
        from massive.rest.models import SnapshotMarketType

        source = make_source()
        source._client.get_snapshot_all.return_value = ["x"]
        assert source._fetch_snapshots(["AAPL"]) == ["x"]
        source._client.get_snapshot_all.assert_called_once_with(
            market_type=SnapshotMarketType.STOCKS, tickers=["AAPL"]
        )


@pytest.mark.skipif(not os.getenv("MASSIVE_API_KEY"), reason="MASSIVE_API_KEY not set")
@pytest.mark.asyncio
async def test_live_smoke():
    """Exercises the real SDK and API. Skipped unless MASSIVE_API_KEY is set."""
    cache = PriceCache()
    source = MassiveDataSource(os.environ["MASSIVE_API_KEY"], cache, poll_interval=60.0)
    await source.start(["AAPL"])
    try:
        assert cache.get("AAPL") is not None
    finally:
        await source.stop()
