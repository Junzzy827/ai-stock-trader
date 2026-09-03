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
    """Emits fixed actions so engine behaviour is isolated from the indicators.

    ``actions`` is either one list applied to every symbol, or a mapping of
    symbol to its own list. ``scores`` sets the conviction the engine ranks
    competing entries by.
    """

    def __init__(self, actions, scores: dict[str, float] | None = None):
        self.actions = actions
        self.scores = scores or {}

    def generate(self, bars, news=None):
        symbol = bars[0].symbol
        actions = self.actions[symbol] if isinstance(self.actions, dict) else self.actions
        score = self.scores.get(symbol, 1.0)
        return [
            Signal(bar.date, bar.symbol, actions[index], score, "stub", score, 0.0)
            for index, bar in enumerate(bars)
        ]
