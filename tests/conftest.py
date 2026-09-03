from datetime import date, timedelta

from ai_stock_trader.domain.models import OHLCV, Signal

START = date(2025, 1, 1)


def bars(prices: list[float], symbol: str = "TEST", start: date | None = None) -> list[OHLCV]:
    """Flat bars where open == high == low == close, one calendar day apart."""
    start = start or START
    return [OHLCV(start + timedelta(days=i), symbol, p, p, p, p) for i, p in enumerate(prices)]


def series(rows: list[tuple[float, float, float, float]], symbol: str = "TEST") -> list[OHLCV]:
    """Bars with explicit open/high/low/close, for stop and gap behaviour."""
    return [OHLCV(START + timedelta(days=i), symbol, *row) for i, row in enumerate(rows)]


class StubStrategy:
    """Emits a fixed action per bar so engine behaviour is isolated."""

    def __init__(self, actions: list[str]):
        self.actions = actions

    def generate(self, bars, news=None):
        return [
            Signal(bar.date, bar.symbol, self.actions[index], 1.0, "stub", 1.0, 0.0)
            for index, bar in enumerate(bars)
        ]
