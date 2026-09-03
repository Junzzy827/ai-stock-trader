from __future__ import annotations

import json
from pathlib import Path

from .backtest import run_backtest
from .models import NewsItem, OHLCV, Trade
from .strategy import TechnicalNewsStrategy


class PaperBroker:
    """Local paper broker. It records decisions and never sends live orders."""

    def __init__(self, initial_cash: float = 100_000, commission_rate: float = 0.001):
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate

    def run(
        self,
        bars: list[OHLCV],
        strategy: TechnicalNewsStrategy,
        log_path: str | Path,
        news: list[NewsItem] | None = None,
    ) -> tuple[Trade, ...]:
        result = run_backtest(bars, strategy, self.initial_cash, self.commission_rate, news)
        path = Path(log_path)
        with path.open("w", encoding="utf-8") as file:
            for trade in result.trades:
                file.write(json.dumps(trade.to_dict(), ensure_ascii=False, default=str) + "\n")
        return result.trades
