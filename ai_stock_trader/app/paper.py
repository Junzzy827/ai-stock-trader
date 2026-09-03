"""Local paper trading. It records decisions and never sends live orders."""

from __future__ import annotations

from pathlib import Path

from ..adapters.store.jsonl import JsonlDecisionStore
from ..domain.market import MarketSpec
from ..domain.models import NewsItem
from ..domain.risk import RiskConfig
from ..domain.strategy import TechnicalNewsStrategy
from .backtest import BacktestResult, PriceData, run_backtest


class PaperBroker:
    def __init__(
        self,
        initial_cash: float = 100_000,
        commission_rate: float = 0.001,
        risk_config: RiskConfig | None = None,
        market: MarketSpec | None = None,
    ):
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.risk_config = risk_config
        self.market = market

    def run(
        self,
        data: PriceData,
        strategy: TechnicalNewsStrategy,
        log_path: str | Path,
        news: list[NewsItem] | None = None,
        append: bool = False,
    ) -> BacktestResult:
        """Replay the bars and write one log line per evaluated symbol-day."""
        with JsonlDecisionStore(log_path, append=append) as store:
            return run_backtest(
                data,
                strategy,
                self.initial_cash,
                self.commission_rate,
                news,
                risk_config=self.risk_config,
                market=self.market,
                store=store,
            )
