"""
Unit tests for src/fetcher.py.

Coverage:
  - is_market_active() with known weekday + time combinations
  - Fetcher.validate() with valid and invalid records
  - Fetcher.serialize() / deserialize() round-trip
  - Fetcher.normalize() for yfinance and alpha_vantage raw dict formats
  - Retry + backoff: verifies each source is tried up to max_retries times
    before the Fetcher gives up and returns None
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from src.fetcher import Fetcher, is_market_active
from src.models import NormalizedRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Build a UTC-aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# IST is UTC+5:30, so market open (09:15 IST) = 03:45 UTC
# and market close (15:30 IST) = 10:00 UTC.

# Wednesday 2024-01-03 is a known Wednesday (weekday=2).
# Reference Wednesday: 2024-01-03

WEDNESDAY = (2024, 1, 3)
SATURDAY = (2024, 1, 6)
SUNDAY = (2024, 1, 7)


# ---------------------------------------------------------------------------
# is_market_active
# ---------------------------------------------------------------------------

class TestIsMarketActive:

    # --- Within trading hours on a weekday ---

    def test_market_open_exact_open_time(self):
        # 09:15 IST = 03:45 UTC on Wed
        now = _utc(*WEDNESDAY, 3, 45)
        assert is_market_active(now) is True

    def test_market_open_mid_session(self):
        # 12:00 IST = 06:30 UTC on Wed
        now = _utc(*WEDNESDAY, 6, 30)
        assert is_market_active(now) is True

    def test_market_open_exact_close_time(self):
        # 15:30 IST = 10:00 UTC on Wed
        now = _utc(*WEDNESDAY, 10, 0)
        assert is_market_active(now) is True

    def test_market_open_monday(self):
        # Monday 2024-01-01, 12:00 IST = 06:30 UTC
        monday = _utc(2024, 1, 1, 6, 30)
        assert is_market_active(monday) is True

    def test_market_open_friday(self):
        # Friday 2024-01-05, 12:00 IST = 06:30 UTC
        friday = _utc(2024, 1, 5, 6, 30)
        assert is_market_active(friday) is True

    # --- Outside trading hours on a weekday ---

    def test_market_closed_before_open(self):
        # 09:14 IST = 03:44 UTC on Wed
        now = _utc(*WEDNESDAY, 3, 44)
        assert is_market_active(now) is False

    def test_market_closed_after_close(self):
        # 15:31 IST = 10:01 UTC on Wed
        now = _utc(*WEDNESDAY, 10, 1)
        assert is_market_active(now) is False

    def test_market_closed_midnight(self):
        # 00:00 IST = 18:30 UTC previous day → still 00:00 on the same calendar
        # date. 00:00 IST = 18:30 UTC Tuesday → but we just need a time well
        # outside trading hours on a weekday.
        # Wednesday at 00:00 UTC = Tuesday 18:30 IST — not a weekday mismatch;
        # time is well outside [09:15, 15:30] IST.
        now = _utc(*WEDNESDAY, 0, 0)
        assert is_market_active(now) is False

    # --- Weekend ---

    def test_market_closed_saturday(self):
        # Saturday at 06:30 UTC = 12:00 IST — right in the middle of what would
        # be trading hours, but it's a weekend.
        now = _utc(*SATURDAY, 6, 30)
        assert is_market_active(now) is False

    def test_market_closed_sunday(self):
        now = _utc(*SUNDAY, 6, 30)
        assert is_market_active(now) is False

    # --- Default (no argument): smoke-test that it doesn't raise ---

    def test_no_argument_does_not_raise(self):
        result = is_market_active()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Fetcher.validate
# ---------------------------------------------------------------------------

class TestFetcherValidate:

    def _record(self, symbol="RELIANCE.NS", price=100.0, timestamp=None):
        ts = timestamp or datetime(2024, 1, 3, 10, 0, 0)
        return NormalizedRecord(symbol=symbol, price=price, timestamp=ts)

    def test_valid_record(self):
        assert Fetcher.validate(self._record()) is True

    def test_invalid_empty_symbol(self):
        assert Fetcher.validate(self._record(symbol="")) is False

    def test_invalid_zero_price(self):
        assert Fetcher.validate(self._record(price=0.0)) is False

    def test_invalid_negative_price(self):
        assert Fetcher.validate(self._record(price=-1.0)) is False

    def test_invalid_none_timestamp(self):
        r = self._record()
        r.timestamp = None  # type: ignore[assignment]
        assert Fetcher.validate(r) is False

    def test_valid_small_price(self):
        assert Fetcher.validate(self._record(price=0.01)) is True

    def test_valid_timezone_aware_timestamp(self):
        ts = datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
        assert Fetcher.validate(self._record(timestamp=ts)) is True

    def test_invalid_bool_price_true(self):
        # bool is a subclass of int in Python; True == 1 but should not be
        # accepted as a valid price.
        r = self._record()
        r.price = True  # type: ignore[assignment]
        assert Fetcher.validate(r) is False

    def test_invalid_bool_price_false(self):
        r = self._record()
        r.price = False  # type: ignore[assignment]
        assert Fetcher.validate(r) is False


# ---------------------------------------------------------------------------
# Fetcher.serialize / deserialize round-trip
# ---------------------------------------------------------------------------

class TestFetcherSerializeDeserialize:

    def _record(self):
        return NormalizedRecord(
            symbol="TCS.NS",
            price=3500.50,
            timestamp=datetime(2024, 6, 15, 9, 30, 0, tzinfo=timezone.utc),
        )

    def test_round_trip_symbol(self):
        r = self._record()
        assert Fetcher.deserialize(Fetcher.serialize(r)).symbol == r.symbol

    def test_round_trip_price(self):
        r = self._record()
        assert Fetcher.deserialize(Fetcher.serialize(r)).price == pytest.approx(r.price)

    def test_round_trip_timestamp(self):
        r = self._record()
        restored = Fetcher.deserialize(Fetcher.serialize(r))
        assert restored.timestamp == r.timestamp

    def test_serialize_produces_valid_json(self):
        r = self._record()
        data = json.loads(Fetcher.serialize(r))
        assert set(data.keys()) == {"symbol", "price", "timestamp"}

    def test_deserialize_raises_on_missing_fields(self):
        with pytest.raises((ValueError, KeyError)):
            Fetcher.deserialize(json.dumps({"symbol": "X"}))

    def test_deserialize_raises_on_invalid_json(self):
        with pytest.raises(Exception):
            Fetcher.deserialize("not-json")

    def test_round_trip_naive_datetime(self):
        r = NormalizedRecord(
            symbol="INFY.NS",
            price=1500.0,
            timestamp=datetime(2024, 3, 10, 12, 0, 0),  # naive
        )
        restored = Fetcher.deserialize(Fetcher.serialize(r))
        assert restored.timestamp == r.timestamp

    def test_round_trip_symbol_with_special_chars(self):
        r = NormalizedRecord(
            symbol="M&M.NS",
            price=1200.0,
            timestamp=datetime(2024, 1, 3, 10, 0),
        )
        restored = Fetcher.deserialize(Fetcher.serialize(r))
        assert restored.symbol == "M&M.NS"


# ---------------------------------------------------------------------------
# Fetcher.normalize
# ---------------------------------------------------------------------------

class TestFetcherNormalize:

    def test_normalize_yfinance_format(self):
        ts = datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
        raw = {"symbol": "RELIANCE.NS", "price": 2800.0, "timestamp": ts, "api_source": "yfinance"}
        record = Fetcher.normalize(raw, "yfinance")
        assert record.symbol == "RELIANCE.NS"
        assert record.price == pytest.approx(2800.0)
        assert record.timestamp == ts

    def test_normalize_alpha_vantage_format(self):
        ts = datetime(2024, 1, 3, 10, 0, 0)
        raw = {"symbol": "INFY.BSE", "price": 1500.5, "timestamp": ts, "api_source": "alpha_vantage"}
        record = Fetcher.normalize(raw, "alpha_vantage")
        assert record.symbol == "INFY.BSE"
        assert record.price == pytest.approx(1500.5)
        assert record.timestamp == ts

    def test_normalize_string_timestamp(self):
        raw = {
            "symbol": "TCS.NS",
            "price": 3400.0,
            "timestamp": "2024-01-03T10:00:00+05:30",
        }
        record = Fetcher.normalize(raw, "yfinance")
        assert record.symbol == "TCS.NS"
        assert record.price == pytest.approx(3400.0)
        assert isinstance(record.timestamp, datetime)

    def test_normalize_missing_symbol_yields_empty(self):
        raw = {"price": 100.0, "timestamp": datetime(2024, 1, 3, 10, 0)}
        record = Fetcher.normalize(raw, "yfinance")
        assert record.symbol == ""

    def test_normalize_missing_price_yields_zero(self):
        raw = {"symbol": "TEST.NS", "timestamp": datetime(2024, 1, 3, 10, 0)}
        record = Fetcher.normalize(raw, "yfinance")
        assert record.price == 0.0

    def test_normalize_invalid_price_yields_zero(self):
        raw = {"symbol": "TEST.NS", "price": "N/A", "timestamp": datetime(2024, 1, 3, 10, 0)}
        record = Fetcher.normalize(raw, "yfinance")
        assert record.price == 0.0

    def test_normalize_produces_normalized_record_type(self):
        raw = {
            "symbol": "WIPRO.NS",
            "price": 450.0,
            "timestamp": datetime(2024, 1, 3, 10, 0),
        }
        record = Fetcher.normalize(raw, "yfinance")
        assert isinstance(record, NormalizedRecord)


# ---------------------------------------------------------------------------
# Retry + exponential backoff
# ---------------------------------------------------------------------------

class TestFetcherRetry:
    """Verify that the Fetcher retries each source up to max_retries times
    and only sleeps between retries (not after the last attempt of a source)."""

    def _make_failing_source(self, name: str) -> MagicMock:
        src = MagicMock()
        src.SOURCE_NAME = name
        src.fetch_company.side_effect = RuntimeError(f"{name} unavailable")
        return src

    def _make_succeeding_source(self, symbol: str, name: str) -> MagicMock:
        src = MagicMock()
        src.SOURCE_NAME = name
        src.fetch_company.return_value = {
            "symbol": symbol,
            "price": 100.0,
            "timestamp": datetime(2024, 1, 3, 10, 0),
            "api_source": name,
        }
        return src

    @patch("src.fetcher._time.sleep")
    def test_single_source_retries_max_retries_times(self, mock_sleep):
        source = self._make_failing_source("source_a")
        fetcher = Fetcher(sources=[source], max_retries=3)
        result = fetcher.fetch_company("RELIANCE.NS")

        assert result is None
        assert source.fetch_company.call_count == 3

    @patch("src.fetcher._time.sleep")
    def test_single_source_backoff_sleep_calls(self, mock_sleep):
        """Sleeps should be 1 s, 2 s (not after the 3rd/final attempt)."""
        source = self._make_failing_source("source_a")
        fetcher = Fetcher(sources=[source], max_retries=3)
        fetcher.fetch_company("RELIANCE.NS")

        # With max_retries=3 (attempts 0,1,2), sleep after attempt 0 and 1:
        # 2**0=1 s and 2**1=2 s. No sleep after attempt 2.
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2**0
        mock_sleep.assert_any_call(2)  # 2**1

    @patch("src.fetcher._time.sleep")
    def test_fallback_to_second_source_on_first_exhausted(self, mock_sleep):
        source_a = self._make_failing_source("source_a")
        source_b = self._make_succeeding_source("RELIANCE.NS", "source_b")
        fetcher = Fetcher(sources=[source_a, source_b], max_retries=3)

        result = fetcher.fetch_company("RELIANCE.NS")

        assert result is not None
        assert result.symbol == "RELIANCE.NS"
        assert source_a.fetch_company.call_count == 3
        assert source_b.fetch_company.call_count == 1

    @patch("src.fetcher._time.sleep")
    def test_all_sources_exhausted_returns_none(self, mock_sleep):
        source_a = self._make_failing_source("source_a")
        source_b = self._make_failing_source("source_b")
        fetcher = Fetcher(sources=[source_a, source_b], max_retries=3)

        result = fetcher.fetch_company("UNKNOWN.NS")

        assert result is None
        assert source_a.fetch_company.call_count == 3
        assert source_b.fetch_company.call_count == 3

    @patch("src.fetcher._time.sleep")
    def test_success_on_first_attempt_no_sleep(self, mock_sleep):
        source = self._make_succeeding_source("TCS.NS", "source_a")
        fetcher = Fetcher(sources=[source], max_retries=3)

        result = fetcher.fetch_company("TCS.NS")

        assert result is not None
        mock_sleep.assert_not_called()

    @patch("src.fetcher._time.sleep")
    def test_success_on_second_attempt_one_sleep(self, mock_sleep):
        source = MagicMock()
        source.SOURCE_NAME = "source_a"
        # Fail once, then succeed
        source.fetch_company.side_effect = [
            RuntimeError("first fail"),
            {
                "symbol": "INFY.NS",
                "price": 1500.0,
                "timestamp": datetime(2024, 1, 3, 10, 0),
                "api_source": "source_a",
            },
        ]
        fetcher = Fetcher(sources=[source], max_retries=3)

        result = fetcher.fetch_company("INFY.NS")

        assert result is not None
        assert result.symbol == "INFY.NS"
        mock_sleep.assert_called_once_with(1)  # slept after attempt 0

    @patch("src.fetcher._time.sleep")
    def test_max_retries_one_attempts_once(self, mock_sleep):
        source = self._make_failing_source("source_a")
        fetcher = Fetcher(sources=[source], max_retries=1)

        result = fetcher.fetch_company("X.NS")

        assert result is None
        assert source.fetch_company.call_count == 1
        mock_sleep.assert_not_called()  # no sleep when max_retries=1
