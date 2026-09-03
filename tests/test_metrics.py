from datetime import date, timedelta

import pytest

from ai_stock_trader.domain.metrics import compute, max_drawdown, round_trips
from ai_stock_trader.domain.models import BUY, SELL, Trade


def curve(values: list[float]) -> list[tuple[date, float]]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=i), value) for i, value in enumerate(values)]


def trade(day: int, action: str, price: float, realized: float) -> Trade:
    return Trade(date(2025, 1, day), "TEST", action, 100, price, 0.0, 0.0, realized, "test")


def test_max_drawdown_measures_the_worst_peak_to_trough():
    assert max_drawdown(curve([100, 120, 90, 130])) == pytest.approx(0.25)


def test_max_drawdown_is_zero_for_a_monotonic_rise():
    assert max_drawdown(curve([100, 110, 120])) == 0.0


def test_round_trips_pair_each_exit_with_its_entry():
    trades = [trade(1, BUY, 100, 0), trade(5, SELL, 120, 2_000), trade(8, BUY, 110, 0)]
    pairs = round_trips(trades)
    assert len(pairs) == 1
    assert (pairs[0][0].date.day, pairs[0][1].date.day) == (1, 5)


def test_compute_reports_win_rate_and_holding_period():
    trades = [trade(1, BUY, 100, 0), trade(5, SELL, 120, 2_000), trade(8, BUY, 110, 0), trade(10, SELL, 100, -1_000)]
    metrics = compute(curve([100_000, 102_000, 101_000]), trades, 100_000, 0.05, 250.0)
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.round_trips == 2
    assert metrics.average_holding_days == pytest.approx(3.0)
    assert metrics.total_commission == 250.0


def test_metrics_are_none_rather_than_zero_when_undefined():
    metrics = compute(curve([100_000]), [], 100_000, 0.0, 0.0)
    assert metrics.sharpe_ratio is None
    assert metrics.win_rate is None
    assert metrics.average_holding_days is None
