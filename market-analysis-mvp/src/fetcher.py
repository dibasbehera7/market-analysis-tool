"""
Fetcher module for the Market Analysis MVP.

Responsibilities:
  - Market-hours detection (NSE trading session: Mon–Fri 09:15–15:30 IST)
  - DataSource protocol and adapter implementations (yfinance, Alpha Vantage)
  - Data normalization, validation, and JSON serialization
  - Retry with exponential backoff and multi-source fallback
  - Batch fetch for all NIFTY 500 companies
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, time, timezone
from typing import Protocol

from zoneinfo import ZoneInfo

from src.models import NormalizedRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Market-hours constants
# ---------------------------------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)   # 09:15 IST
MARKET_CLOSE = time(15, 30)  # 15:30 IST
MARKET_DAYS = {0, 1, 2, 3, 4}  # Monday–Friday (weekday() values)

# NIFTY 500 symbols — abbreviated list for MVP; populated from a static
# list or fetched dynamically in a real deployment.
NIFTY500_SYMBOLS: list[str] = []  # populated at runtime / via configuration


# ---------------------------------------------------------------------------
# Market-hours pure function (injectable for testing)
# ---------------------------------------------------------------------------

def is_market_active(now_utc: datetime | None = None) -> bool:
    """Return True if *now_utc* falls within NSE equity trading hours.

    NSE trading hours: Monday–Friday, 09:15–15:30 IST (Asia/Kolkata).
    Public holidays are not modelled in the MVP.

    Args:
        now_utc: A UTC (or timezone-aware) datetime to test.  Defaults to
                 ``datetime.utcnow()`` when *None* is passed.  Pass an
                 explicit value in tests to avoid mocking system time.

    Returns:
        True iff the corresponding IST local time falls on a weekday and
        within the half-open interval [MARKET_OPEN, MARKET_CLOSE].
    """
    if now_utc is None:
        now_utc = datetime.now(tz=timezone.utc)

    now_ist = now_utc.astimezone(IST)

    if now_ist.weekday() not in MARKET_DAYS:
        return False

    t = now_ist.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


# ---------------------------------------------------------------------------
# DataSource protocol
# ---------------------------------------------------------------------------

class DataSource(Protocol):
    """Interface that every market-data adapter must satisfy."""

    def fetch_company(self, symbol: str) -> dict:
        """Fetch raw market data for *symbol*.

        Returns:
            A raw dict whose schema depends on the underlying API.  The
            Fetcher normalises this into a :class:`NormalizedRecord`.

        Raises:
            Exception: Any error from the underlying API call.
        """
        ...

    def is_market_active(self) -> bool:
        """Return True if the market is currently in an active trading session."""
        ...


# ---------------------------------------------------------------------------
# Adapter: yfinance
# ---------------------------------------------------------------------------

class YFinanceAdapter:
    """DataSource adapter backed by the yfinance library (Yahoo Finance)."""

    SOURCE_NAME = "yfinance"

    def is_market_active(self) -> bool:
        return is_market_active()

    def fetch_company(self, symbol: str) -> dict:
        """Fetch latest price data for *symbol* via yfinance.

        For intraday data we use a 1-day period with 1-minute intervals;
        for EOD we use a 5-day period.  The most recent row is returned as
        a dict with keys: ``symbol``, ``price``, ``timestamp``,
        ``api_source``.

        Args:
            symbol: NSE ticker symbol (e.g. ``"RELIANCE.NS"``).

        Returns:
            Raw dict with ``symbol``, ``price``, ``timestamp``,
            ``api_source`` keys.

        Raises:
            RuntimeError: If no data is returned by yfinance.
            ImportError: If yfinance is not installed.
        """
        import yfinance as yf  # deferred import so the module loads without yfinance

        period = "1d"
        interval = "1m" if self.is_market_active() else "1d"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            raise RuntimeError(f"yfinance returned no data for symbol '{symbol}'")

        last_row = hist.iloc[-1]
        return {
            "symbol": symbol,
            "price": float(last_row["Close"]),
            "timestamp": last_row.name.to_pydatetime(),
            "api_source": self.SOURCE_NAME,
        }


# ---------------------------------------------------------------------------
# Adapter: Alpha Vantage
# ---------------------------------------------------------------------------

class AlphaVantageAdapter:
    """DataSource adapter backed by the alpha_vantage Python wrapper."""

    SOURCE_NAME = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def is_market_active(self) -> bool:
        return is_market_active()

    def fetch_company(self, symbol: str) -> dict:
        """Fetch latest price data for *symbol* via Alpha Vantage.

        Uses the TIME_SERIES_INTRADAY (1min) endpoint during market hours
        and TIME_SERIES_DAILY for EOD data.

        Args:
            symbol: Ticker symbol (e.g. ``"RELIANCE.BSE"``).

        Returns:
            Raw dict with ``symbol``, ``price``, ``timestamp``,
            ``api_source`` keys.

        Raises:
            RuntimeError: If no data is returned or rate-limited.
            ImportError: If alpha_vantage is not installed.
        """
        from alpha_vantage.timeseries import TimeSeries  # deferred import

        ts = TimeSeries(key=self._api_key, output_format="pandas")

        if self.is_market_active():
            data, _ = ts.get_intraday(symbol=symbol, interval="1min", outputsize="compact")
        else:
            data, _ = ts.get_daily(symbol=symbol, outputsize="compact")

        if data is None or data.empty:
            raise RuntimeError(
                f"alpha_vantage returned no data for symbol '{symbol}'"
            )

        last_row = data.iloc[-1]
        # Alpha Vantage column names differ by endpoint; normalise to "close".
        close_col = next(
            (c for c in last_row.index if "close" in c.lower()),
            last_row.index[0],
        )
        price = float(last_row[close_col])
        timestamp = datetime.fromisoformat(str(data.index[-1]))

        return {
            "symbol": symbol,
            "price": price,
            "timestamp": timestamp,
            "api_source": self.SOURCE_NAME,
        }


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

class Fetcher:
    """Fetches, normalises, validates, and serialises NIFTY 500 market data.

    Args:
        sources:     Ordered list of :class:`DataSource` adapters.  The
                     Fetcher tries them left-to-right with retry before
                     moving to the next source.
        max_retries: Number of retry attempts per source (default 3).
                     Backoff schedule: attempt *k* sleeps ``2**k`` seconds
                     (0 → 1 s, 1 → 2 s, 2 → 4 s).
        symbols:     Optional explicit list of NIFTY 500 symbols to fetch.
                     Falls back to the module-level ``NIFTY500_SYMBOLS``
                     list when not provided.
    """

    def __init__(
        self,
        sources: list[DataSource],
        max_retries: int = 3,
        symbols: list[str] | None = None,
    ) -> None:
        self._sources = sources
        self._max_retries = max_retries
        self._symbols = symbols if symbols is not None else NIFTY500_SYMBOLS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_nifty500(self) -> list[NormalizedRecord]:
        """Fetch data for all configured NIFTY 500 company symbols.

        Companies that cannot be fetched from any source after all retries
        are logged and skipped; the pipeline continues with remaining
        companies.

        Returns:
            List of :class:`NormalizedRecord` objects, one per
            successfully fetched company.
        """
        records: list[NormalizedRecord] = []
        for symbol in self._symbols:
            record = self.fetch_company(symbol)
            if record is not None:
                records.append(record)
        return records

    def fetch_company(self, symbol: str) -> NormalizedRecord | None:
        """Fetch and normalise data for a single company.

        Retry schedule (per source):
          attempt 0 → sleep 1 s  (2**0)
          attempt 1 → sleep 2 s  (2**1)
          attempt 2 → sleep 4 s  (2**2)

        When all retries across all sources are exhausted the error is
        logged with the company symbol and ``None`` is returned so the
        calling pipeline can skip this company and continue.

        Args:
            symbol: NSE/BSE ticker symbol.

        Returns:
            A validated :class:`NormalizedRecord`, or ``None`` on total
            failure.
        """
        for source in self._sources:
            source_name = type(source).__name__
            for attempt in range(self._max_retries):
                try:
                    raw = source.fetch_company(symbol)
                    record = self.normalize(raw, getattr(source, "SOURCE_NAME", source_name))
                    if self.validate(record):
                        return record
                    logger.warning(
                        "Fetcher: normalized record for '%s' failed validation "
                        "(source=%s, attempt=%d); retrying.",
                        symbol,
                        source_name,
                        attempt,
                    )
                except Exception as exc:
                    logger.warning(
                        "Fetcher: error fetching '%s' from %s (attempt %d/%d): %s",
                        symbol,
                        source_name,
                        attempt + 1,
                        self._max_retries,
                        exc,
                    )

                # Exponential backoff before the next retry; skip sleep after
                # the final attempt of a source to avoid unnecessary waiting
                # before switching sources.
                if attempt < self._max_retries - 1:
                    backoff = 2 ** attempt  # 1 s, 2 s, 4 s
                    _time.sleep(backoff)

        logger.error(
            "Fetcher: all sources exhausted for company '%s'; skipping.",
            symbol,
        )
        return None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def normalize(raw_data: dict, api_source: str) -> NormalizedRecord:
        """Normalise an API-specific raw dict into a :class:`NormalizedRecord`.

        Supported raw dict formats:

        * **yfinance / generic**: keys ``symbol``, ``price``,
          ``timestamp``.
        * **Alpha Vantage**: same keys produced by
          :class:`AlphaVantageAdapter`.

        If ``symbol`` is absent or cannot be extracted, the record is
        created with an empty symbol so that :meth:`validate` will reject
        it and the error can be logged with the ``"[unknown]"`` placeholder.

        Args:
            raw_data:   Dict returned by a :class:`DataSource` adapter.
            api_source: Human-readable source label (e.g. ``"yfinance"``).

        Returns:
            A :class:`NormalizedRecord` (may be invalid; callers should
            call :meth:`validate` before using the record).
        """
        symbol = raw_data.get("symbol", "")
        if not isinstance(symbol, str):
            symbol = str(symbol) if symbol is not None else ""

        price_raw = raw_data.get("price")
        try:
            price = float(price_raw) if price_raw is not None else 0.0
        except (TypeError, ValueError):
            price = 0.0

        ts_raw = raw_data.get("timestamp")
        if isinstance(ts_raw, datetime):
            timestamp = ts_raw
        elif isinstance(ts_raw, str):
            try:
                timestamp = datetime.fromisoformat(ts_raw)
            except ValueError:
                timestamp = datetime(1970, 1, 1)  # sentinel; will fail validation
        else:
            timestamp = datetime(1970, 1, 1)

        return NormalizedRecord(symbol=symbol, price=price, timestamp=timestamp)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate(record: NormalizedRecord) -> bool:
        """Validate a :class:`NormalizedRecord`.

        A record is valid iff:
          * ``symbol`` is a non-empty string
          * ``price`` is a strictly positive finite float
          * ``timestamp`` is a non-null :class:`datetime` instance

        When the symbol is absent or empty, the error is logged with the
        ``"[unknown]"`` placeholder so operators can diagnose data-source
        issues.

        Args:
            record: The record to validate.

        Returns:
            ``True`` if the record passes all checks; ``False`` otherwise.
        """
        symbol_ok = isinstance(record.symbol, str) and len(record.symbol) > 0
        price_ok = (
            isinstance(record.price, (int, float))
            and not isinstance(record.price, bool)
            and record.price > 0
        )
        timestamp_ok = isinstance(record.timestamp, datetime)

        if not symbol_ok:
            symbol_label = record.symbol if isinstance(record.symbol, str) else "[unknown]"
            logger.error(
                "Fetcher.validate: record with symbol '%s' has invalid symbol field.",
                symbol_label or "[unknown]",
            )
        if not price_ok:
            logger.error(
                "Fetcher.validate: record '%s' has invalid price: %s.",
                record.symbol or "[unknown]",
                record.price,
            )
        if not timestamp_ok:
            logger.error(
                "Fetcher.validate: record '%s' has invalid timestamp: %s.",
                record.symbol or "[unknown]",
                record.timestamp,
            )

        return symbol_ok and price_ok and timestamp_ok

    # ------------------------------------------------------------------
    # Serialisation helpers (delegates to NormalizedRecord)
    # ------------------------------------------------------------------

    @staticmethod
    def serialize(record: NormalizedRecord) -> str:
        """Serialize *record* to a JSON string.

        Delegates to :meth:`NormalizedRecord.serialize`.

        Args:
            record: A :class:`NormalizedRecord` instance.

        Returns:
            JSON-encoded string.
        """
        return record.serialize()

    @staticmethod
    def deserialize(json_str: str) -> NormalizedRecord:
        """Deserialize a JSON string back to a :class:`NormalizedRecord`.

        Delegates to :meth:`NormalizedRecord.deserialize`.

        Args:
            json_str: A string previously produced by :meth:`serialize`.

        Returns:
            Restored :class:`NormalizedRecord`.

        Raises:
            ValueError: If required fields are missing.
            json.JSONDecodeError: If the string is not valid JSON.
        """
        return NormalizedRecord.deserialize(json_str)
