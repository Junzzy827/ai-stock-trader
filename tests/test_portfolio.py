from datetime import date

import pytest

from ai_stock_trader.domain.models import BUY, SELL, Fill
from ai_stock_trader.domain.portfolio import Portfolio

DAY = date(2025, 1, 1)


def fill(side: str, quantity: int, price: float, commission: float = 0.0) -> Fill:
    return Fill(DAY, "TEST", side, quantity, price, commission)


def test_buy_reduces_cash_by_notional_plus_commission():
    portfolio = Portfolio(100_000)
    portfolio.apply(fill(BUY, 100, 500, commission=50))
    assert portfolio.cash == pytest.approx(49_950)
    assert portfolio.quantity("TEST") == 100


def test_second_buy_averages_the_entry_price():
    portfolio = Portfolio(100_000)
    portfolio.apply(fill(BUY, 100, 400))
    portfolio.apply(fill(BUY, 100, 600))
    assert portfolio.position("TEST").avg_price == pytest.approx(500)


def test_sell_realizes_pnl_net_of_commission_and_closes_the_position():
    portfolio = Portfolio(100_000)
    portfolio.apply(fill(BUY, 100, 500))
    realized = portfolio.apply(fill(SELL, 100, 600, commission=60))
    assert realized == pytest.approx(100 * 100 - 60)
    assert portfolio.position("TEST") is None
    assert portfolio.realized_pnl == pytest.approx(9_940)


def test_equity_marks_open_positions_to_the_supplied_price():
    portfolio = Portfolio(100_000)
    portfolio.apply(fill(BUY, 100, 500))
    assert portfolio.equity({"TEST": 700}) == pytest.approx(50_000 + 70_000)


def test_buying_beyond_available_cash_is_rejected():
    portfolio = Portfolio(1_000)
    with pytest.raises(ValueError):
        portfolio.apply(fill(BUY, 100, 500))


def test_selling_more_than_held_is_rejected():
    portfolio = Portfolio(100_000)
    portfolio.apply(fill(BUY, 100, 500))
    with pytest.raises(ValueError):
        portfolio.apply(fill(SELL, 200, 500))
