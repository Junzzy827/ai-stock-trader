from datetime import date, timedelta

from ai_stock_trader.domain.models import OHLCV


def bars(prices: list[float], symbol: str = "TEST", start: date | None = None) -> list[OHLCV]:
    """Flat bars where open == high == low == close, one calendar day apart."""
    start = start or date(2025, 1, 1)
    return [OHLCV(start + timedelta(days=i), symbol, p, p, p, p) for i, p in enumerate(prices)]
