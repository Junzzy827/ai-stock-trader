from datetime import date, timedelta

import pytest
from conftest import START, StubStrategy, bars

from ai_stock_trader.adapters.broker.simulated import SimulatedBroker
from ai_stock_trader.app.engine import run_engine
from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.models import BUY, HOLD, OHLCV, SELL
from ai_stock_trader.domain.portfolio import Portfolio
from ai_stock_trader.domain.risk import RiskConfig, RiskManager
from ai_stock_trader.domain.universe import Universe

SPEC = MarketSpec(lot_size=100, commission_rate=0.0)


def run(universe, actions, scores=None, risk_config=None, cash=100_000):
    return run_engine(
        universe=Universe.of(universe),
        strategy=StubStrategy(actions, scores),
        portfolio=Portfolio(cash),
        risk=RiskManager(risk_config or RiskConfig(max_positions=2), SPEC),
        broker=SimulatedBroker(SPEC),
    )


def two_symbols(length: int = 3) -> list[OHLCV]:
    return bars([100] * length, "A") + bars([100] * length, "B")


def test_both_symbols_can_be_held_within_the_position_limit():
    result = run(two_symbols(), {"A": [BUY, HOLD, HOLD], "B": [BUY, HOLD, HOLD]},
                 risk_config=RiskConfig(max_position_weight=0.5, max_positions=2))
    assert sorted(result.portfolio.positions) == ["A", "B"]


def test_the_position_limit_stops_the_lower_conviction_entry():
    result = run(
        two_symbols(),
        {"A": [BUY, HOLD, HOLD], "B": [BUY, HOLD, HOLD]},
        scores={"A": 0.9, "B": 0.2},
        risk_config=RiskConfig(max_position_weight=0.5, max_positions=1),
    )
    assert list(result.portfolio.positions) == ["A"]
    skipped = [d for d in result.decisions if d.symbol == "B" and d.note]
    assert skipped[0].note == "position limit reached"


def test_scarce_cash_goes_to_the_stronger_signal_not_the_first_symbol():
    winner = run(two_symbols(), {"A": [BUY, HOLD, HOLD], "B": [BUY, HOLD, HOLD]}, scores={"A": 0.2, "B": 0.9})
    assert list(winner.portfolio.positions) == ["B"]

    reversed_scores = run(two_symbols(), {"A": [BUY, HOLD, HOLD], "B": [BUY, HOLD, HOLD]}, scores={"A": 0.9, "B": 0.2})
    assert list(reversed_scores.portfolio.positions) == ["A"]


def test_an_exit_frees_cash_for_an_entry_on_the_same_day():
    universe = two_symbols(4)
    result = run(universe, {"A": [BUY, HOLD, SELL, HOLD], "B": [HOLD, HOLD, BUY, HOLD]})
    same_day = [trade for trade in result.trades if trade.date == START + timedelta(days=3)]
    assert [(trade.symbol, trade.action) for trade in same_day] == [("A", SELL), ("B", BUY)]
    assert list(result.portfolio.positions) == ["B"]


def test_one_decision_is_recorded_per_symbol_and_date():
    result = run(two_symbols(3), [HOLD] * 3)
    assert len(result.decisions) == 4  # two symbols, two executable dates
    assert {(d.date, d.symbol) for d in result.decisions} == {
        (START + timedelta(days=offset), symbol) for offset in (1, 2) for symbol in ("A", "B")
    }


def test_a_symbol_without_a_bar_that_day_is_skipped_and_the_other_still_trades():
    days = [START, START + timedelta(days=1), START + timedelta(days=2)]
    a = [OHLCV(day, "A", 100, 100, 100, 100) for day in days]
    b = [OHLCV(days[0], "B", 100, 100, 100, 100), OHLCV(days[2], "B", 100, 100, 100, 100)]
    result = run({"A": a, "B": b}, {"A": [BUY, HOLD, HOLD], "B": [HOLD, HOLD, HOLD]})
    on_second_day = [d.symbol for d in result.decisions if d.date == days[1]]
    assert on_second_day == ["A"]


def test_equity_carries_a_stale_symbol_forward_at_its_last_close():
    days = [START + timedelta(days=offset) for offset in range(3)]
    a = [OHLCV(days[0], "A", 100, 100, 100, 100), OHLCV(days[1], "A", 100, 100, 100, 100)]
    b = [OHLCV(day, "B", 50, 50, 50, 50) for day in days]
    result = run({"A": a, "B": b}, {"A": [BUY, HOLD], "B": [HOLD, HOLD, HOLD]})
    # A stops trading after day 2 but is still held, so equity must not drop it.
    assert result.equity_curve[-1][1] == pytest.approx(100_000)


def test_the_pending_signal_of_every_symbol_is_returned():
    result = run(two_symbols(3), {"A": [HOLD, HOLD, BUY], "B": [HOLD, HOLD, SELL]})
    assert {(signal.symbol, signal.action) for signal in result.pending_signals} == {("A", BUY), ("B", SELL)}
