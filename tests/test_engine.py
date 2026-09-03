from datetime import date, timedelta

import pytest

from ai_stock_trader.adapters.broker.simulated import SimulatedBroker
from ai_stock_trader.app.engine import run_engine
from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.models import BUY, HOLD, OHLCV, SELL, Signal
from ai_stock_trader.domain.portfolio import Portfolio
from ai_stock_trader.domain.risk import RiskConfig, RiskManager

SPEC = MarketSpec(lot_size=100, commission_rate=0.0)
START = date(2025, 1, 1)


class StubStrategy:
    """Emits a fixed action per bar so engine behaviour is isolated."""

    def __init__(self, actions: list[str]):
        self.actions = actions

    def generate(self, bars, news=None):
        return [
            Signal(bar.date, bar.symbol, self.actions[index], 1.0, "stub", 1.0, 0.0)
            for index, bar in enumerate(bars)
        ]


def series(rows: list[tuple[float, float, float, float]]) -> list[OHLCV]:
    return [OHLCV(START + timedelta(days=i), "TEST", *row) for i, row in enumerate(rows)]


def run(bars, actions, risk_config=None, cash=100_000):
    return run_engine(
        bars=bars,
        strategy=StubStrategy(actions),
        portfolio=Portfolio(cash),
        risk=RiskManager(risk_config or RiskConfig(), SPEC),
        broker=SimulatedBroker(SPEC),
    )


def test_stop_loss_exits_when_the_bar_trades_through_the_trigger():
    bars = series([(100, 100, 100, 100), (100, 101, 99, 100), (98, 99, 94, 96), (96, 97, 95, 96)])
    result = run(bars, [BUY, HOLD, HOLD, HOLD], RiskConfig(stop_loss_pct=0.05))
    assert [trade.action for trade in result.trades] == [BUY, SELL]
    exit_trade = result.trades[1]
    assert exit_trade.price == 95
    assert exit_trade.date == START + timedelta(days=2)
    assert result.portfolio.quantity("TEST") == 0


def test_position_is_untouched_while_the_stop_is_not_hit():
    bars = series([(100, 100, 100, 100), (100, 101, 99, 100), (100, 102, 96, 101)])
    result = run(bars, [BUY, HOLD, HOLD], RiskConfig(stop_loss_pct=0.05))
    assert [trade.action for trade in result.trades] == [BUY]
    assert result.portfolio.quantity("TEST") > 0


def test_no_re_entry_on_the_same_bar_as_a_stop_out():
    bars = series([(100, 100, 100, 100), (100, 101, 99, 100), (98, 99, 94, 96)])
    result = run(bars, [BUY, BUY, BUY], RiskConfig(stop_loss_pct=0.05))
    assert [trade.action for trade in result.trades] == [BUY, SELL]
    assert result.decisions[-1].note == "stopped out"


def test_every_evaluated_bar_produces_a_decision_record():
    bars = series([(100, 100, 100, 100)] * 4)
    result = run(bars, [HOLD] * 4)
    assert len(result.decisions) == len(bars) - 1
    assert all(decision.action == HOLD for decision in result.decisions)


def test_hold_days_record_why_nothing_was_traded():
    bars = series([(100, 100, 100, 100)] * 3)
    result = run(bars, [SELL, SELL, SELL])
    assert result.decisions[0].note == "nothing to sell"


def test_pending_signal_is_the_last_bar_without_an_execution_bar():
    bars = series([(100, 100, 100, 100)] * 3)
    result = run(bars, [HOLD, HOLD, BUY])
    assert result.pending_signal.action == BUY
    assert result.pending_signal.date == bars[-1].date


def test_equity_curve_starts_at_the_initial_cash():
    bars = series([(100, 100, 100, 100)] * 3)
    result = run(bars, [HOLD] * 3, cash=250_000)
    assert result.equity_curve[0] == (bars[0].date, 250_000)


def test_trailing_stop_locks_in_gains_after_a_rally():
    bars = series([(100, 100, 100, 100), (100, 100, 100, 100), (120, 120, 120, 120), (110, 112, 105, 106)])
    result = run(bars, [BUY, HOLD, HOLD, HOLD], RiskConfig(trailing_stop_pct=0.1))
    # Peak close 120 arms a stop at 108, which the final bar trades through.
    assert result.trades[-1].action == SELL
    assert result.trades[-1].price == pytest.approx(108)
