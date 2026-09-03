"""Turns strategy intent into sized orders.

The strategy says *what* it wants; this layer decides *how much*, applying
lot sizing, exposure caps and protective stops. Keeping the two apart means a
strategy change can never silently alter position sizing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Mapping

from .market import JAPAN, MarketSpec
from .models import BUY, MARKET, SELL, STOP, Order, Signal
from .portfolio import Portfolio


@dataclass(frozen=True)
class RiskConfig:
    max_position_weight: float = 1.0
    cash_buffer: float = 0.0
    stop_loss_pct: float | None = None
    trailing_stop_pct: float | None = None
    max_positions: int = 1

    def __post_init__(self) -> None:
        if not 0 < self.max_position_weight <= 1:
            raise ValueError("max_position_weight must be in (0, 1]")
        if not 0 <= self.cash_buffer < 1:
            raise ValueError("cash_buffer must be in [0, 1)")
        for name in ("stop_loss_pct", "trailing_stop_pct"):
            value = getattr(self, name)
            if value is not None and not 0 < value < 1:
                raise ValueError(f"{name} must be in (0, 1)")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")


class RiskManager:
    def __init__(self, config: RiskConfig | None = None, market: MarketSpec | None = None):
        self.config = config or RiskConfig()
        self.market = market or JAPAN

    def protective_orders(self, portfolio: Portfolio, as_of: Date) -> list[Order]:
        """Standing stop orders for open positions, placed before the bar trades."""
        orders: list[Order] = []
        for position in portfolio.positions.values():
            if position.quantity > 0 and position.stop_price is not None:
                orders.append(
                    Order(
                        date=as_of,
                        symbol=position.symbol,
                        side=SELL,
                        quantity=position.quantity,
                        order_type=STOP,
                        trigger_price=position.stop_price,
                        reason=f"stop at {position.stop_price:.2f}",
                    )
                )
        return orders

    def plan(
        self,
        signal: Signal,
        portfolio: Portfolio,
        prices: Mapping[str, float],
        as_of: Date,
    ) -> list[Order]:
        held = portfolio.quantity(signal.symbol)
        if signal.action == SELL and held > 0:
            return [Order(as_of, signal.symbol, SELL, held, MARKET, None, signal.reason)]
        if signal.action != BUY or held > 0:
            return []
        if len(portfolio.positions) >= self.config.max_positions:
            return []
        reference_price = prices.get(signal.symbol)
        if not reference_price or reference_price <= 0:
            return []
        quantity = self._entry_quantity(portfolio, prices, reference_price)
        if quantity <= 0:
            return []
        return [Order(as_of, signal.symbol, BUY, quantity, MARKET, None, signal.reason)]

    def _entry_quantity(self, portfolio: Portfolio, prices: Mapping[str, float], reference_price: float) -> int:
        spendable = portfolio.cash * (1 - self.config.cash_buffer)
        exposure_cap = portfolio.equity(prices) * self.config.max_position_weight
        budget = min(spendable, exposure_cap)
        lot_cost = reference_price * self.market.lot_size * (1 + self.market.commission_rate)
        if lot_cost <= 0:
            return 0
        return int(budget // lot_cost) * self.market.lot_size

    def update_stops(self, portfolio: Portfolio, prices: Mapping[str, float]) -> None:
        """Arm the initial stop after entry and ratchet the trailing stop up."""
        for symbol, position in portfolio.positions.items():
            price = prices.get(symbol)
            if price is None:
                continue
            position.peak_price = max(position.peak_price, price)
            candidates = [position.stop_price] if position.stop_price is not None else []
            if self.config.stop_loss_pct is not None:
                candidates.append(position.avg_price * (1 - self.config.stop_loss_pct))
            if self.config.trailing_stop_pct is not None:
                candidates.append(position.peak_price * (1 - self.config.trailing_stop_pct))
            if candidates:
                position.stop_price = max(candidates)
