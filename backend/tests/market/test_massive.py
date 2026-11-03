"""Tests for MassiveDataSource and parse_snapshot.

Snapshots are built with the real SDK model (TickerSnapshot.from_dict) rather
than bare MagicMocks, so attribute-name mistakes against the SDK are caught.
"""

from unittest.mock import MagicMock, patch

import pytest
from massive.exceptions import AuthError, BadResponse
from massive.rest.models import TickerSnapshot

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource, parse_snapshot

T_NS = 1_707_580_800_500_000_000  # 2024-02-10T16:00:00.5Z in nanoseconds


def snap(
    ticker,
    price=None,
    t_ns=None,
    prev_close=None,
    minute_close=None,
    day_close=None,
    updated=None,
) -> TickerSnapshot:
    d: dict = {"ticker": ticker}
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


def make_source(tickers=("AAPL",), poll_interval=60.0) -> tuple[MassiveDataSource, PriceCache]:
    cache = PriceCache()
    source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=poll_interval)
    source._tickers = list(tickers)
    source._client = MagicMock()  # satisfy the _poll_once guard
    return source, cache


class TestParseSnapshot:
    def test_uses_last_trade_and_ns_timestamp(self):
        assert parse_snapshot(snap("AAPL", 190.5, t_ns=T_NS, prev_close=189.0)) == (
            "AAPL",
            190.5,
            1_707_580_800.5,
            189.0,
        )

    def test_falls_back_to_minute_close_and_updated(self):
        result = parse_snapshot(snap("MSFT", minute_close=410.0, updated=1_000_000_000_000_000_000))
        assert result == ("MSFT", 410.0, 1_000_000_000.0, None)

    def test_falls_back_to_day_close(self):
        _, price, _, _ = parse_snapshot(snap("MSFT", day_close=405.0, updated=1))
        assert price == 405.0

    def test_falls_back_to_prev_close_as_last_resort(self):
        _, price, _, session_open = parse_snapshot(snap("MSFT", prev_close=400.0))
        assert price == 400.0
        assert session_open == 400.0

    def test_zero_price_is_skipped_in_fallback_chain(self):
        _, price, _, _ = parse_snapshot(snap("MSFT", price=0.0, minute_close=410.0))
        assert price == 410.0

    def test_missing_timestamp_uses_now(self):
        with patch("app.market.massive_client.time.time", return_value=123.0):
            _, _, ts, _ = parse_snapshot(snap("AAPL", 190.0))
        assert ts == 123.0

    def test_returns_none_without_any_price(self):
        assert parse_snapshot(snap("ZZZZ")) is None

    def test_returns_none_without_ticker(self):
        assert parse_snapshot(TickerSnapshot.from_dict({"lastTrade": {"p": 1.0}})) is None

    def test_ticker_uppercased(self):
        assert parse_snapshot(snap("aapl", 1.0))[0] == "AAPL"


@pytest.mark.asyncio
class TestMassiveDataSource:
    async def test_poll_updates_cache(self):
        source, cache = make_source(["AAPL", "GOOGL"])
        snaps = [snap("AAPL", 190.50, t_ns=T_NS), snap("GOOGL", 175.25, t_ns=T_NS)]
        with patch.object(source, "_fetch_snapshots", return_value=snaps):
            await source._poll_once()
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25
        assert cache.get("AAPL").timestamp == 1_707_580_800.5

    async def test_poll_writes_session_open(self):
        source, cache = make_source()
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 191.0, t_ns=1, prev_close=190.0)]
        ):
            await source._poll_once()
        u = cache.get("AAPL")
        assert u.price == 191.0 and u.session_open == 190.0
        assert u.day_change_percent == 0.5263

    async def test_unusable_snapshot_skipped(self):
        source, cache = make_source(["AAPL", "BAD"])
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 190.5), snap("BAD")]
        ):
            await source._poll_once()
        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("BAD") is None

    async def test_untracked_ticker_in_response_ignored(self):
        source, cache = make_source(["AAPL"])
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("AAPL", 1.0), snap("MSFT", 2.0)]
        ):
            await source._poll_once()
        assert "MSFT" not in cache

    async def test_removed_ticker_not_resurrected_by_inflight_poll(self):
        source, cache = make_source(["AAPL"])

        def fetch(_tickers):
            source._tickers = []  # simulate remove_ticker during the HTTP call
            return [snap("AAPL", 191.0)]

        with patch.object(source, "_fetch_snapshots", side_effect=fetch):
            await source._poll_once()
        assert "AAPL" not in cache

    @pytest.mark.parametrize(
        "exc",
        [RuntimeError("network error"), AuthError("bad key"), BadResponse("429")],
    )
    async def test_api_errors_do_not_crash(self, exc):
        source, cache = make_source()
        with patch.object(source, "_fetch_snapshots", side_effect=exc):
            await source._poll_once()  # must not raise
        assert cache.get_price("AAPL") is None
        assert source._consecutive_failures == 1

    async def test_backoff_grows_caps_and_resets(self):
        source, _ = make_source(poll_interval=15)
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

    async def test_fetch_passes_tickers_to_sdk(self):
        source, _ = make_source(["AAPL", "MSFT"])
        source._client.get_snapshot_all.return_value = []
        await source._poll_once()
        kwargs = source._client.get_snapshot_all.call_args.kwargs
        assert kwargs["tickers"] == ["AAPL", "MSFT"]

    async def test_add_ticker_normalizes(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        await source.add_ticker("  aapl ")
        assert source.get_tickers() == ["AAPL"]

    async def test_add_ticker_rejects_invalid(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        with pytest.raises(ValueError):
            await source.add_ticker("$$$")

    async def test_add_duplicate_is_noop(self):
        source, _ = make_source(["AAPL"])
        with patch.object(source, "_fetch_snapshots") as fetch:
            await source.add_ticker("aapl")
            fetch.assert_not_called()
        assert source.get_tickers() == ["AAPL"]

    async def test_add_ticker_polls_immediately_for_new_ticker_only(self):
        source, cache = make_source(["AAPL"])
        with patch.object(
            source, "_fetch_snapshots", return_value=[snap("PYPL", 62.0)]
        ) as fetch:
            await source.add_ticker("PYPL")
        fetch.assert_called_once_with(["PYPL"])
        assert cache.get_price("PYPL") == 62.0
        assert source.get_tickers() == ["AAPL", "PYPL"]

    async def test_remove_ticker(self):
        source, cache = make_source(["AAPL", "GOOGL"])
        cache.update("AAPL", 190.00)
        await source.remove_ticker("aapl")
        assert source.get_tickers() == ["GOOGL"]
        assert cache.get("AAPL") is None

    async def test_empty_tickers_skips_poll(self):
        source, _ = make_source([])
        with patch.object(source, "_fetch_snapshots") as fetch:
            await source._poll_once()
            fetch.assert_not_called()

    async def test_stop_is_idempotent(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        await source.stop()
        await source.stop()

    async def test_start_immediate_poll_and_stop(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[snap("AAPL", 190.50)]):
                await source.start(["aapl", "AAPL"])
        assert source.get_tickers() == ["AAPL"]
        assert cache.get_price("AAPL") == 190.50
        assert source._task is not None and not source._task.done()
        await source.stop()
        assert source._task is None
