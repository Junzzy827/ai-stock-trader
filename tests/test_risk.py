from datetime import date

import pytest

from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.models import BUY, SELL, STOP, Fill, Signal
from ai_stock_trader.domain.portfolio import Portfolio
from ai_stock_trader.domain.risk import RiskConfig, RiskManager

DAY = date(2025, 1, 6)
MARKET_SPEC = MarketSpec(lot_size=100, commission_rate=0.0)


def signal(action: str) -> Signal:
    return Signal(DAY, "TEST", action, 0.5, "test", 0.5, 0.0)


def test_entry_is_rounded_down_to_whole_lots():
    manager = RiskManager(RiskConfig(), MARKET_SPEC)
    portfolio = Portfolio(100_000)
    orders = manager.plan(signal(BUY), portfolio, {"TEST": 330}, DAY)
    assert orders[0].quantity == 300  # 303 shares affordable, rounded to 3 lots


def test_no_order_when_one_lot_is_unaffordable():
    manager = RiskManager(RiskConfig(), MARKET_SPEC)
    assert manager.plan(signal(BUY), Portfolio(10_000), {"TEST": 330}, DAY) == []


def test_cash_buffer_and_max_weight_shrink_the_order():
    manager = RiskManager(RiskConfig(max_position_weight=0.5, cash_buffer=0.1), MARKET_SPEC)
    orders = manager.plan(signal(BUY), Portfolio(100_000), {"TEST": 100}, DAY)
    assert orders[0].quantity == 500  # 50% of equity binds before the cash buffer


def test_buy_is_skipped_while_already_holding():
    manager = RiskManager(RiskConfig(), MARKET_SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    assert manager.plan(signal(BUY), portfolio, {"TEST": 100}, DAY) == []


def test_sell_exits_the_entire_position():
    manager = RiskManager(RiskConfig(), MARKET_SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 300, 100))
    orders = manager.plan(signal(SELL), portfolio, {"TEST": 100}, DAY)
    assert (orders[0].side, orders[0].quantity) == (SELL, 300)


def test_stop_loss_is_armed_from_the_entry_price():
    manager = RiskManager(RiskConfig(stop_loss_pct=0.05), MARKET_SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    manager.update_stops(portfolio, {"TEST": 100})
    assert portfolio.position("TEST").stop_price == pytest.approx(95)
    orders = manager.protective_orders(portfolio, DAY)
    assert orders[0].order_type == STOP


def test_trailing_stop_only_ratchets_up():
    manager = RiskManager(RiskConfig(trailing_stop_pct=0.1), MARKET_SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    manager.update_stops(portfolio, {"TEST": 120})
    assert portfolio.position("TEST").stop_price == pytest.approx(108)
    manager.update_stops(portfolio, {"TEST": 105})
    assert portfolio.position("TEST").stop_price == pytest.approx(108)


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        RiskConfig(max_position_weight=1.5)
    with pytest.raises(ValueError):
        RiskConfig(stop_loss_pct=0)
