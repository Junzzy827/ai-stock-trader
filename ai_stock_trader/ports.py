"""Interfaces the core defines and adapters implement.

These are Protocols only: importing this module pulls in no I/O and no third
party package, so the core stays substitutable (CSV or J-Quants prices,
simulated or paper broker, JSONL or SQLite storage).
"""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .domain.models import Decision, Fill, NewsItem, OHLCV, Order
from .domain.portfolio import Portfolio


class PriceSource(Protocol):
    def prices(self, symbol: str) -> list[OHLCV]: ...


class NewsSource(Protocol):
    def news(self, symbol: str) -> list[NewsItem]: ...


class NewsAnalyzer(Protocol):
    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]: ...


class Broker(Protocol):
    def execute(self, orders: Sequence[Order], bar: OHLCV, portfolio: Portfolio) -> list[Fill]: ...


class DecisionStore(Protocol):
    def record(self, decision: Decision) -> None: ...

    def close(self) -> None: ...
