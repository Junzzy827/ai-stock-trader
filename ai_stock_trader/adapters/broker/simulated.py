"""Fill model for daily bars.

Backtesting and paper trading share this broker, so the only difference
between them is which bars the engine is fed and where decisions are stored.
A live broker would implement the same ``Broker`` port.
"""

from __future__ import annotations

from typing import Sequence

from ...domain.market import JAPAN, MarketSpec
from ...domain.models import BUY, MARKET, OHLCV, SELL, STOP, Fill, Order
from ...domain.portfolio import Portfolio


class SimulatedBroker:
    def __init__(self, market: MarketSpec | None = None, slippage_rate: float = 0.0):
        if slippage_rate < 0:
            raise ValueError("slippage_rate must not be negative")
        self.market = market or JAPAN
        self.slippage_rate = slippage_rate

    def execute(self, orders: Sequence[Order], bar: OHLCV, portfolio: Portfolio) -> list[Fill]:
        available_cash = portfolio.cash
        available_quantity = {symbol: position.quantity for symbol, position in portfolio.positions.items()}
        fills: list[Fill] = []
        for order in orders:
            price = self._fill_price(order, bar)
            if price is None or price <= 0:
                continue
            if order.side == BUY:
                quantity = self._affordable_quantity(order.quantity, price, available_cash)
                if quantity <= 0:
                    continue
                available_cash -= quantity * price + self.market.commission(quantity * price)
            else:
                quantity = min(order.quantity, available_quantity.get(order.symbol, 0))
                if quantity <= 0:
                    continue
                available_quantity[order.symbol] -= quantity
            fills.append(
                Fill(
                    date=bar.date,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=quantity,
                    price=price,
                    commission=self.market.commission(quantity * price),
                    order_type=order.order_type,
                    reason=order.reason,
                )
            )
        return fills

    def _fill_price(self, order: Order, bar: OHLCV) -> float | None:
        if order.order_type == MARKET:
            direction = 1 if order.side == BUY else -1
            return bar.open * (1 + direction * self.slippage_rate)
        if order.order_type == STOP:
            trigger = order.trigger_price
            if trigger is None:
                return None
            if order.side == SELL:
                if bar.low > trigger:
                    return None
                # A gap below the stop fills at the open, not at the trigger.
                return min(bar.open, trigger) * (1 - self.slippage_rate)
            if bar.high < trigger:
                return None
            return max(bar.open, trigger) * (1 + self.slippage_rate)
        raise ValueError(f"unsupported order type: {order.order_type}")

    def _affordable_quantity(self, quantity: int, price: float, cash: float) -> int:
        quantity = self.market.round_to_lot(quantity)
        while quantity > 0 and quantity * price + self.market.commission(quantity * price) > cash:
            quantity -= self.market.lot_size
        return max(quantity, 0)
