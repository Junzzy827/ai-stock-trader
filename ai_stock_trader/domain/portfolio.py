"""Cash, positions and realized P&L. The single source of truth for state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import BUY, SELL, Fill


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0
    stop_price: float | None = None
    peak_price: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_price) * self.quantity


class Portfolio:
    def __init__(self, cash: float):
        if cash <= 0:
            raise ValueError("cash must be positive")
        self.initial_cash = float(cash)
        self.cash = float(cash)
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_commission = 0.0

    def position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def quantity(self, symbol: str) -> int:
        position = self.positions.get(symbol)
        return position.quantity if position else 0

    def apply(self, fill: Fill) -> float:
        """Apply a fill and return the realized P&L it produced."""
        if fill.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        self.total_commission += fill.commission
        if fill.side == BUY:
            cost = fill.notional + fill.commission
            if cost > self.cash + 1e-9:
                raise ValueError("insufficient cash for fill")
            self.cash -= cost
            position = self.positions.setdefault(fill.symbol, Position(fill.symbol))
            total_quantity = position.quantity + fill.quantity
            position.avg_price = (position.avg_price * position.quantity + fill.notional) / total_quantity
            position.quantity = total_quantity
            position.peak_price = max(position.peak_price, fill.price)
            return 0.0
        if fill.side != SELL:
            raise ValueError(f"unknown fill side: {fill.side}")
        position = self.positions.get(fill.symbol)
        if position is None or position.quantity < fill.quantity:
            raise ValueError("cannot sell more than the held quantity")
        realized = (fill.price - position.avg_price) * fill.quantity - fill.commission
        self.cash += fill.notional - fill.commission
        self.realized_pnl += realized
        position.quantity -= fill.quantity
        if position.quantity == 0:
            del self.positions[fill.symbol]
        return realized

    def equity(self, prices: Mapping[str, float]) -> float:
        held = 0.0
        for symbol, position in self.positions.items():
            price = prices.get(symbol)
            if price is None:
                raise KeyError(f"no price supplied for held symbol {symbol}")
            held += position.market_value(price)
        return self.cash + held
