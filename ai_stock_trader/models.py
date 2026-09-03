from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class OHLCV:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class NewsItem:
    published_at: date
    title: str
    summary: str = ""
    url: str = ""


@dataclass(frozen=True)
class Signal:
    date: date
    symbol: str
    action: str  # BUY, SELL, or HOLD
    score: float
    reason: str
    technical_score: float
    news_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Trade:
    date: date
    symbol: str
    action: str
    quantity: int
    price: float
    cash_after: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    initial_cash: float
    final_cash: float
    final_equity: float
    return_rate: float
    buy_and_hold_return_rate: float
    trades: tuple[Trade, ...]
    signals: tuple[Signal, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_cash": self.initial_cash,
            "final_cash": self.final_cash,
            "final_equity": self.final_equity,
            "return_rate": self.return_rate,
            "buy_and_hold_return_rate": self.buy_and_hold_return_rate,
            "trades": [trade.to_dict() for trade in self.trades],
            "signals": [signal.to_dict() for signal in self.signals],
        }

