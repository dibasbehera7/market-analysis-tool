"""
Unit tests for src/analyzer.py — task 4.8.

Coverage:
  - generate_insight() builds correct Insight with expected field values
  - generate_insight() summary string format for all TrendType values
  - generate_insight() handles None metrics gracefully in summary
  - analyze() pipeline wires metrics + trend + insight correctly
  - analyze() NPA computed only for bank companies
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.analyzer import Analyzer
from src.models import (
    CompanyFinancials,
    CompanyMetrics,
    Insight,
    Trend,
    TrendType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(
    symbol: str = "RELIANCE.NS",
    pe_ratio: float | None = 15.0,
    pb_ratio: float | None = 2.5,
    roe: float | None = 0.18,
    eps_growth: float | None = 12.5,
    npa: float | None = None,
) -> CompanyMetrics:
    return CompanyMetrics(
        symbol=symbol,
        pe_ratio=pe_ratio,
        pb_ratio=pb_ratio,
        roe=roe,
        eps_growth=eps_growth,
        npa=npa,
    )


def _trend(
    symbol: str = "RELIANCE.NS",
    trend_type: TrendType = TrendType.BULLISH,
    support_level: float | None = 2000.0,
    resistance_level: float | None = 3000.0,
) -> Trend:
    return Trend(
        symbol=symbol,
        trend_type=trend_type,
        support_level=support_level,
        resistance_level=resistance_level,
    )


def _financials(
    symbol: str = "RELIANCE.NS",
    eps: float = 100.0,
    bvps: float = 500.0,
    net_income: float = 50000.0,
    equity: float = 300000.0,
    eps_history: list[float] | None = None,
    is_bank: bool = False,
    npa: float | None = None,
    total_assets: float | None = None,
) -> CompanyFinancials:
    return CompanyFinancials(
        symbol=symbol,
        earnings_per_share=eps,
        book_value_per_share=bvps,
        net_income=net_income,
        shareholder_equity=equity,
        eps_history=eps_history or [10.0, 11.0, 12.0, 13.0],
        is_bank=is_bank,
        non_performing_assets=npa,
        total_assets=total_assets,
    )


# ---------------------------------------------------------------------------
# generate_insight — field correctness
# ---------------------------------------------------------------------------

class TestGenerateInsight:

    def setup_method(self):
        self.analyzer = Analyzer()

    def test_returns_insight_instance(self):
        insight = self.analyzer.generate_insight("RELIANCE.NS", _metrics(), _trend(), 2500.0)
        assert isinstance(insight, Insight)

    def test_symbol_propagated(self):
        insight = self.analyzer.generate_insight("TCS.NS", _metrics("TCS.NS"), _trend("TCS.NS"), 3500.0)
        assert insight.symbol == "TCS.NS"

    def test_metrics_propagated(self):
        m = _metrics()
        insight = self.analyzer.generate_insight("RELIANCE.NS", m, _trend(), 2500.0)
        assert insight.metrics is m

    def test_trend_propagated(self):
        t = _trend()
        insight = self.analyzer.generate_insight("RELIANCE.NS", _metrics(), t, 2500.0)
        assert insight.trend is t

    def test_current_price_propagated(self):
        insight = self.analyzer.generate_insight("RELIANCE.NS", _metrics(), _trend(), 2750.50)
        assert insight.current_price == pytest.approx(2750.50)

    def test_summary_is_string(self):
        insight = self.analyzer.generate_insight("RELIANCE.NS", _metrics(), _trend(), 2500.0)
        assert isinstance(insight.summary, str)
        assert len(insight.summary) > 0

    # --- Summary content ---

    def test_summary_starts_with_bullish(self):
        insight = self.analyzer.generate_insight(
            "X.NS", _metrics(), _trend(trend_type=TrendType.BULLISH), 100.0
        )
        assert insight.summary.startswith("BULLISH trend")

    def test_summary_starts_with_bearish(self):
        insight = self.analyzer.generate_insight(
            "X.NS", _metrics(), _trend(trend_type=TrendType.BEARISH), 100.0
        )
        assert insight.summary.startswith("BEARISH trend")

    def test_summary_starts_with_neutral(self):
        insight = self.analyzer.generate_insight(
            "X.NS", _metrics(), _trend(trend_type=TrendType.NEUTRAL), 100.0
        )
        assert insight.summary.startswith("NEUTRAL trend")

    def test_summary_contains_pe_when_present(self):
        m = _metrics(pe_ratio=15.2)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "P/E: 15.20" in insight.summary

    def test_summary_contains_pb_when_present(self):
        m = _metrics(pb_ratio=2.1)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "P/B: 2.10" in insight.summary

    def test_summary_contains_roe_when_present(self):
        m = _metrics(roe=0.18)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "ROE: 0.18" in insight.summary

    def test_summary_contains_eps_growth_when_present(self):
        m = _metrics(eps_growth=12.5)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "EPS growth: 12.50%" in insight.summary

    def test_summary_contains_npa_when_present(self):
        m = _metrics(npa=3.75)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "NPA: 3.75%" in insight.summary

    def test_summary_omits_none_pe(self):
        m = _metrics(pe_ratio=None)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "P/E" not in insight.summary

    def test_summary_omits_none_pb(self):
        m = _metrics(pb_ratio=None)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "P/B" not in insight.summary

    def test_summary_omits_none_roe(self):
        m = _metrics(roe=None)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(), 100.0)
        assert "ROE" not in insight.summary

    def test_summary_only_trend_when_all_metrics_none(self):
        m = _metrics(pe_ratio=None, pb_ratio=None, roe=None, eps_growth=None, npa=None)
        insight = self.analyzer.generate_insight("X.NS", m, _trend(trend_type=TrendType.NEUTRAL), 100.0)
        assert insight.summary == "NEUTRAL trend"


# ---------------------------------------------------------------------------
# analyze() pipeline
# ---------------------------------------------------------------------------

class TestAnalyzePipeline:

    def setup_method(self):
        self.analyzer = Analyzer()

    # Build a price list long enough to trigger BULLISH/BEARISH (>= 200 prices)
    @staticmethod
    def _bullish_prices(n: int = 250) -> list[float]:
        # Rising prices: long MA will be lower than short MA
        return [float(100 + i) for i in range(n)]

    @staticmethod
    def _bearish_prices(n: int = 250) -> list[float]:
        # Falling prices: short MA will be lower than long MA
        return [float(100 + n - i) for i in range(n)]

    @staticmethod
    def _short_prices(n: int = 10) -> list[float]:
        return [100.0] * n

    def test_returns_insight_instance(self):
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), self._bullish_prices(), 2500.0)
        assert isinstance(insight, Insight)

    def test_symbol_set_correctly(self):
        insight = self.analyzer.analyze("TCS.NS", _financials("TCS.NS"), self._bullish_prices(), 3500.0)
        assert insight.symbol == "TCS.NS"

    def test_current_price_set_correctly(self):
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), self._bullish_prices(), 2800.0)
        assert insight.current_price == pytest.approx(2800.0)

    def test_bullish_trend_detected(self):
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), self._bullish_prices(), 2500.0)
        assert insight.trend.trend_type == TrendType.BULLISH

    def test_bearish_trend_detected(self):
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), self._bearish_prices(), 2500.0)
        assert insight.trend.trend_type == TrendType.BEARISH

    def test_neutral_trend_for_short_price_history(self):
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), self._short_prices(), 2500.0)
        assert insight.trend.trend_type == TrendType.NEUTRAL

    def test_support_level_is_min_of_prices(self):
        prices = self._bullish_prices(250)
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), prices, 2500.0)
        assert insight.trend.support_level == pytest.approx(min(prices[-252:]))

    def test_resistance_level_is_max_of_prices(self):
        prices = self._bullish_prices(250)
        insight = self.analyzer.analyze("RELIANCE.NS", _financials(), prices, 2500.0)
        assert insight.trend.resistance_level == pytest.approx(max(prices[-252:]))

    def test_pe_ratio_computed_correctly(self):
        # price=2500, eps=100 → P/E = 25.0
        fin = _financials(eps=100.0)
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.pe_ratio == pytest.approx(25.0)

    def test_pb_ratio_computed_correctly(self):
        # price=2500, bvps=500 → P/B = 5.0
        fin = _financials(bvps=500.0)
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.pb_ratio == pytest.approx(5.0)

    def test_roe_computed_correctly(self):
        # net_income=50000, equity=250000 → ROE = 0.2
        fin = _financials(net_income=50000.0, equity=250000.0)
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.roe == pytest.approx(0.2)

    def test_eps_growth_computed_correctly(self):
        # history [10, 11, 12, 20] → growth = (20-10)/10*100 = 100.0
        fin = _financials(eps_history=[10.0, 11.0, 12.0, 20.0])
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.eps_growth == pytest.approx(100.0)

    def test_npa_computed_for_bank(self):
        # npa=5000, total_assets=100000 → NPA = 5.0%
        fin = _financials(is_bank=True, npa=5000.0, total_assets=100000.0)
        insight = self.analyzer.analyze("BANKBARODA.NS", fin, self._short_prices(), 200.0)
        assert insight.metrics.npa == pytest.approx(5.0)

    def test_npa_none_for_non_bank(self):
        fin = _financials(is_bank=False, npa=5000.0, total_assets=100000.0)
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.npa is None

    def test_npa_none_when_bank_missing_assets(self):
        fin = _financials(is_bank=True, npa=None, total_assets=None)
        insight = self.analyzer.analyze("BANKBARODA.NS", fin, self._short_prices(), 200.0)
        assert insight.metrics.npa is None

    def test_zero_denominator_yields_none_pe(self):
        fin = _financials(eps=0.0)
        insight = self.analyzer.analyze("RELIANCE.NS", fin, self._short_prices(), 2500.0)
        assert insight.metrics.pe_ratio is None

    def test_metrics_symbol_matches_insight_symbol(self):
        insight = self.analyzer.analyze("INFY.NS", _financials("INFY.NS"), self._short_prices(), 1500.0)
        assert insight.metrics.symbol == "INFY.NS"
        assert insight.trend.symbol == "INFY.NS"
