from datetime import date

import pytest
from conftest import StubStrategy, bars, series

from ai_stock_trader.adapters.store.sqlite import SqliteStore
from ai_stock_trader.app.daily import run_daily
from ai_stock_trader.app.status import account_status
from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.models import BUY, HOLD, SELL
from ai_stock_trader.domain.risk import RiskConfig

SPEC = MarketSpec(lot_size=100, commission_rate=0.0)


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "trader.db"


def daily(db_path, price_bars, actions, risk_config=None, cash=1_000_000):
    with SqliteStore(db_path) as store:
        return run_daily(
            store,
            price_bars,
            StubStrategy(actions),
            initial_cash=cash,
            risk_config=risk_config,
            market=SPEC,
        )


def test_the_first_run_backfills_the_available_history(db_path):
    result = daily(db_path, bars([100] * 5), [HOLD] * 5)
    assert result.account_created is True
    assert len(result.processed_dates) == 4
    assert result.last_processed_date == date(2025, 1, 5)


def test_a_second_run_on_the_same_data_changes_nothing(db_path):
    daily(db_path, bars([100] * 5), [HOLD] * 5)
    repeat = daily(db_path, bars([100] * 5), [HOLD] * 5)
    assert repeat.up_to_date is True
    assert repeat.processed_dates == ()
    assert repeat.account_created is False


def test_only_the_new_bars_are_executed_on_the_next_run(db_path):
    daily(db_path, bars([100] * 5), [HOLD] * 7)
    result = daily(db_path, bars([100] * 7), [HOLD] * 7)
    assert [day.day for day in result.processed_dates] == [6, 7]


def test_cash_and_positions_survive_a_restart(db_path):
    first = daily(db_path, bars([100] * 3), [BUY, HOLD, HOLD])
    assert first.positions[0].quantity == 10_000

    second = daily(db_path, bars([100] * 5), [BUY, HOLD, HOLD, HOLD, HOLD])
    assert second.positions[0].quantity == 10_000
    assert second.cash == pytest.approx(first.cash)
    assert [trade.action for trade in second.trades] == []  # already holding, no re-entry


def test_an_armed_stop_survives_a_restart_and_fires_later(db_path):
    warmup = series([(100, 100, 100, 100)] * 3)
    first = daily(db_path, warmup, [BUY, HOLD, HOLD], RiskConfig(stop_loss_pct=0.05))
    assert first.positions[0].stop_price == pytest.approx(95)

    later = series([(100, 100, 100, 100)] * 3 + [(98, 99, 94, 96)])
    second = daily(db_path, later, [BUY, HOLD, HOLD, HOLD], RiskConfig(stop_loss_pct=0.05))
    assert [trade.action for trade in second.trades] == [SELL]
    assert second.trades[0].price == pytest.approx(95)
    assert second.positions == ()


def test_a_full_replay_and_an_incremental_run_reach_the_same_state(db_path, tmp_path):
    prices = [100, 100, 101, 103, 106, 104, 108]
    actions = [BUY, HOLD, HOLD, HOLD, SELL, HOLD, BUY]
    for cutoff in range(2, len(prices) + 1):
        incremental = daily(db_path, bars(prices[:cutoff]), actions[:cutoff])

    replayed = daily(tmp_path / "replay.db", bars(prices), actions)
    assert replayed.cash == pytest.approx(incremental.cash)
    assert replayed.equity == pytest.approx(incremental.equity)
    assert [p.quantity for p in replayed.positions] == [p.quantity for p in incremental.positions]


def test_the_latest_signal_is_stored_as_the_next_session_proposal(db_path):
    result = daily(db_path, bars([100] * 4), [HOLD, HOLD, HOLD, BUY])
    assert result.pending_signal.action == BUY
    with SqliteStore(db_path) as store:
        proposal = store.latest_proposal()
    assert (proposal["action"], proposal["status"]) == (BUY, "PROPOSED")


def test_status_reports_the_stored_account(db_path):
    daily(db_path, bars([100, 100, 110]), [BUY, HOLD, HOLD])
    with SqliteStore(db_path) as store:
        status = account_status(store, recent=2)
    assert status.exists is True
    assert status.positions[0]["symbol"] == "TEST"
    assert len(status.recent_decisions) == 2
    assert status.metrics.trade_count == 1
    # There is no single instrument to compare a whole account against.
    assert status.metrics.buy_and_hold_return_rate is None


def test_status_of_an_unknown_account_is_empty_rather_than_an_error(db_path):
    with SqliteStore(db_path, "nobody") as store:
        status = account_status(store)
    assert status.exists is False
    assert status.positions == ()


def test_a_single_bar_cannot_be_executed(db_path):
    with SqliteStore(db_path) as store:
        with pytest.raises(ValueError):
            run_daily(store, bars([100]), StubStrategy([HOLD]))
