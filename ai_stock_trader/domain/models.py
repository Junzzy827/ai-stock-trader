"""Pure data structures shared by every layer.

Nothing in ``domain`` performs I/O, so these types stay usable from the
backtester, the paper runner and (later) the web API without change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"

MARKET = "MARKET"
STOP = "STOP"


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
    """What the strategy wants, without any notion of size or money."""

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
class Order:
    """A sized instruction produced by the risk layer, not by the strategy."""

    date: date
    symbol: str
    side: str
    quantity: int
    order_type: str = MARKET
    trigger_price: float | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Fill:
    date: date
    symbol: str
    side: str
    quantity: int
    price: float
    commission: float = 0.0
    order_type: str = MARKET
    reason: str = ""

    @property
    def notional(self) -> float:
        return self.quantity * self.price

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Trade:
    """A fill enriched with the portfolio state it produced."""

    date: date
    symbol: str
    action: str
    quantity: int
    price: float
    commission: float
    cash_after: float
    realized_pnl: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    """One record per evaluated bar, including the days nothing happened.

    Semi-automatic operation needs the reason a trade did *not* happen just as
    much as the trades themselves, so HOLD days are first-class records.
    """

    date: date
    symbol: str
    action: str
    score: float
    reason: str
    technical_score: float
    news_score: float
    orders: tuple[Order, ...] = ()
    fills: tuple[Fill, ...] = ()
    position_quantity: int = 0
    position_avg_price: float = 0.0
    stop_price: float | None = None
    cash: float = 0.0
    equity: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
