from datetime import date

import pytest
from conftest import START

from ai_stock_trader.adapters.store.sqlite import APPROVED, REJECTED, SqliteStore
from ai_stock_trader.domain.models import BUY, MARKET, SELL, STOP, Decision, Fill, Order, Signal, Trade
from ai_stock_trader.domain.portfolio import Portfolio


@pytest.fixture()
def store(tmp_path):
    with SqliteStore(tmp_path / "trader.db") as opened:
        yield opened


def stocked_portfolio() -> Portfolio:
    portfolio = Portfolio(1_000_000)
    portfolio.apply(Fill(START, "TEST", BUY, 300, 100, commission=30))
    position = portfolio.position("TEST")
    position.stop_price = 95.0
    position.peak_price = 110.0
    return portfolio


def test_a_missing_account_loads_as_none(store):
    assert store.load_portfolio() is None
    assert store.last_processed_date() is None


def test_portfolio_round_trips_including_armed_stops(store):
    store.save_portfolio(stocked_portfolio(), date(2025, 1, 10))
    store.commit()

    restored = store.load_portfolio()
    assert restored.cash == pytest.approx(1_000_000 - 30_030)
    assert restored.total_commission == pytest.approx(30)
    position = restored.position("TEST")
    assert (position.quantity, position.avg_price) == (300, 100)
    assert (position.stop_price, position.peak_price) == (95.0, 110.0)
    assert store.last_processed_date() == date(2025, 1, 10)


def test_closed_positions_are_not_left_behind(store):
    portfolio = stocked_portfolio()
    store.save_portfolio(portfolio, date(2025, 1, 10))
    portfolio.apply(Fill(START, "TEST", SELL, 300, 120))
    store.save_portfolio(portfolio, date(2025, 1, 11))
    store.commit()
    assert store.load_portfolio().positions == {}


def test_decisions_round_trip_with_their_orders_and_fills(store):
    decision = Decision(
        date=date(2025, 1, 6),
        symbol="TEST",
        action=BUY,
        score=0.4,
        reason="stub",
        technical_score=0.4,
        news_score=0.0,
        orders=(Order(date(2025, 1, 6), "TEST", SELL, 300, STOP, 95.0, "stop at 95.00"),),
        fills=(Fill(date(2025, 1, 6), "TEST", BUY, 300, 100, 30, MARKET, "stub"),),
        position_quantity=300,
        position_avg_price=100.0,
        stop_price=95.0,
        cash=1_000.0,
        equity=31_000.0,
        note="",
    )
    store.record(decision)
    store.commit()
    assert store.decisions() == [decision]


def test_recording_the_same_day_twice_replaces_rather_than_duplicates(store):
    def decision(note: str) -> Decision:
        return Decision(date(2025, 1, 6), "TEST", BUY, 0.4, "stub", 0.4, 0.0, note=note)

    store.record(decision("first"))
    store.record(decision("second"))
    store.commit()
    stored = store.decisions()
    assert len(stored) == 1
    assert stored[0].note == "second"


def test_decisions_are_returned_oldest_first_within_the_limit(store):
    for day in range(1, 6):
        store.record(Decision(date(2025, 1, day), "TEST", BUY, 0.0, "stub", 0.0, 0.0))
    store.commit()
    assert [d.date.day for d in store.decisions(limit=2)] == [4, 5]


def test_identical_trades_are_stored_once(store):
    trade = Trade(date(2025, 1, 6), "TEST", BUY, 300, 100, 30, 1_000, 0.0, "stub")
    store.record_trade(trade)
    store.record_trade(trade)
    store.commit()
    assert store.trades() == [trade]


def test_equity_history_is_ordered_and_deduplicated(store):
    store.record_equity(date(2025, 1, 7), 101_000, 1_000)
    store.record_equity(date(2025, 1, 6), 100_000, 500)
    store.record_equity(date(2025, 1, 7), 102_000, 1_000)
    store.commit()
    assert store.equity_curve() == [(date(2025, 1, 6), 100_000), (date(2025, 1, 7), 102_000)]


def test_a_proposal_can_be_approved_by_a_human(store):
    store.record_proposal(Signal(date(2025, 1, 8), "TEST", BUY, 0.3, "stub", 0.3, 0.0))
    store.commit()
    assert store.latest_proposal()["status"] == "PROPOSED"

    assert store.decide_proposal(date(2025, 1, 8), "TEST", APPROVED, "checked") is True
    store.commit()
    proposal = store.latest_proposal()
    assert (proposal["status"], proposal["note"]) == (APPROVED, "checked")
    assert proposal["decided_at"] is not None


def test_deciding_an_unknown_proposal_reports_no_match(store):
    assert store.decide_proposal(date(2020, 1, 1), "TEST", REJECTED) is False


def test_re_recording_a_proposal_keeps_the_human_verdict(store):
    signal = Signal(date(2025, 1, 8), "TEST", BUY, 0.3, "stub", 0.3, 0.0)
    store.record_proposal(signal)
    store.decide_proposal(date(2025, 1, 8), "TEST", REJECTED, "見送り")
    store.record_proposal(signal)
    store.commit()
    assert store.latest_proposal()["status"] == REJECTED


def test_uncommitted_writes_are_discarded_on_rollback(store):
    store.record(Decision(date(2025, 1, 6), "TEST", BUY, 0.0, "stub", 0.0, 0.0))
    store.save_portfolio(stocked_portfolio(), date(2025, 1, 6))
    store.rollback()
    assert store.decisions() == []
    assert store.load_portfolio() is None


def test_accounts_in_one_file_do_not_see_each_other(tmp_path):
    path = tmp_path / "trader.db"
    with SqliteStore(path, "alice") as alice:
        alice.save_portfolio(stocked_portfolio(), date(2025, 1, 10))
        alice.commit()
    with SqliteStore(path, "bob") as bob:
        assert bob.load_portfolio() is None
