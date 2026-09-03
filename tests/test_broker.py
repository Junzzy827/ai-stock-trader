from datetime import date

import pytest

from ai_stock_trader.adapters.broker.simulated import SimulatedBroker
from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.models import BUY, MARKET, OHLCV, SELL, STOP, Fill, Order
from ai_stock_trader.domain.portfolio import Portfolio

DAY = date(2025, 1, 6)
SPEC = MarketSpec(lot_size=100, commission_rate=0.0)


def bar(open_: float, high: float, low: float, close: float) -> OHLCV:
    return OHLCV(DAY, "TEST", open_, high, low, close)


def test_market_order_fills_at_the_open():
    broker = SimulatedBroker(SPEC)
    fills = broker.execute([Order(DAY, "TEST", BUY, 100)], bar(100, 110, 95, 105), Portfolio(100_000))
    assert fills[0].price == 100


def test_slippage_moves_the_fill_against_the_order():
    broker = SimulatedBroker(SPEC, slippage_rate=0.01)
    fills = broker.execute([Order(DAY, "TEST", BUY, 100)], bar(100, 110, 95, 105), Portfolio(100_000))
    assert fills[0].price == pytest.approx(101)


def test_quantity_is_clamped_to_what_the_cash_can_buy():
    broker = SimulatedBroker(MarketSpec(lot_size=100, commission_rate=0.01))
    fills = broker.execute([Order(DAY, "TEST", BUY, 1_000)], bar(100, 110, 95, 105), Portfolio(50_000))
    assert fills[0].quantity == 400  # 500 lots' worth of cash cannot cover the commission


def test_stop_order_does_not_fill_above_the_trigger():
    broker = SimulatedBroker(SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    order = Order(DAY, "TEST", SELL, 100, STOP, 95)
    assert broker.execute([order], bar(100, 110, 96, 105), portfolio) == []


def test_stop_order_fills_at_the_trigger_when_the_bar_trades_through_it():
    broker = SimulatedBroker(SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    fills = broker.execute([Order(DAY, "TEST", SELL, 100, STOP, 95)], bar(98, 99, 94, 96), portfolio)
    assert fills[0].price == 95


def test_stop_order_fills_at_the_open_when_the_price_gaps_below_it():
    broker = SimulatedBroker(SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    fills = broker.execute([Order(DAY, "TEST", SELL, 100, STOP, 95)], bar(90, 92, 88, 91), portfolio)
    assert fills[0].price == 90


def test_sell_never_exceeds_the_held_quantity():
    broker = SimulatedBroker(SPEC)
    portfolio = Portfolio(100_000)
    portfolio.apply(Fill(DAY, "TEST", BUY, 100, 100))
    fills = broker.execute([Order(DAY, "TEST", SELL, 500, MARKET)], bar(100, 110, 95, 105), portfolio)
    assert fills[0].quantity == 100
