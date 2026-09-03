"""Interfaces the core defines and adapters implement.

These are Protocols only: importing this module pulls in no I/O and no third
party package, so the core stays substitutable (CSV or J-Quants prices,
simulated or paper broker, JSONL or SQLite storage).
"""

from __future__ import annotations

from datetime import date as Date
from typing import Iterable, Protocol, Sequence

from .domain.models import Decision, Fill, NewsItem, OHLCV, Order, Signal, Trade
from .domain.portfolio import Portfolio


class PriceSource(Protocol):
    def prices(self, symbol: str) -> list[OHLCV]: ...

    def symbols(self) -> list[str]: ...


class NewsSource(Protocol):
    def news(self, symbol: str) -> list[NewsItem]: ...


class NewsAnalyzer(Protocol):
    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]: ...


class Broker(Protocol):
    def execute(self, orders: Sequence[Order], bar: OHLCV, portfolio: Portfolio) -> list[Fill]: ...


class DecisionStore(Protocol):
    def record(self, decision: Decision) -> None: ...

    def close(self) -> None: ...


class StateStore(Protocol):
    """A decision store that also persists the account it belongs to.

    Writes are expected to stay in one transaction until ``commit``, so an
    interrupted run leaves ``last_processed_date`` unadvanced and is simply
    redone on the next run.
    """

    account: str

    def record(self, decision: Decision) -> None: ...

    def record_trade(self, trade: Trade) -> None: ...

    def record_equity(self, day: Date, equity: float, cash: float) -> None: ...

    def record_proposal(self, signal: Signal) -> None: ...

    def load_portfolio(self) -> Portfolio | None: ...

    def save_portfolio(self, portfolio: Portfolio, last_processed: Date | None) -> None: ...

    def last_processed_date(self) -> Date | None: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...
