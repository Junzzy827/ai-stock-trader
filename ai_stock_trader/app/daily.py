"""Incremental daily run: the operating entry point for paper trading.

``run_daily`` loads the stored portfolio, evaluates only the bars that appeared
since the last run, and persists the result atomically. It shares
``run_engine`` with the backtester, so a day traded live follows exactly the
path it would have followed in a backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

from ..adapters.broker.simulated import SimulatedBroker
from ..domain.market import JAPAN, MarketSpec
from ..domain.models import Decision, NewsItem, OHLCV, Signal, Trade
from ..domain.portfolio import Portfolio, Position
from ..domain.risk import RiskConfig, RiskManager
from ..domain.strategy import TechnicalNewsStrategy
from ..ports import StateStore
from .engine import run_engine


@dataclass(frozen=True)
class DailyRunResult:
    account: str
    account_created: bool
    processed_dates: tuple[Date, ...]
    trades: tuple[Trade, ...]
    decisions: tuple[Decision, ...]
    positions: tuple[Position, ...]
    cash: float
    equity: float
    last_processed_date: Date | None
    pending_signal: Signal | None

    @property
    def up_to_date(self) -> bool:
        return not self.processed_dates

    def to_dict(self) -> dict:
        return {
            "account": self.account,
            "account_created": self.account_created,
            "up_to_date": self.up_to_date,
            "processed_dates": [day.isoformat() for day in self.processed_dates],
            "trades": [trade.to_dict() for trade in self.trades],
            "positions": [
                {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "avg_price": position.avg_price,
                    "stop_price": position.stop_price,
                }
                for position in self.positions
            ],
            "cash": self.cash,
            "equity": self.equity,
            "last_processed_date": self.last_processed_date.isoformat() if self.last_processed_date else None,
            # The latest bar has no execution bar yet: this is the next session's candidate.
            "pending_signal": self.pending_signal.to_dict() if self.pending_signal else None,
        }


def run_daily(
    store: StateStore,
    bars: list[OHLCV],
    strategy: TechnicalNewsStrategy,
    *,
    initial_cash: float = 1_000_000,
    risk_config: RiskConfig | None = None,
    market: MarketSpec | None = None,
    slippage_rate: float = 0.0,
    news: list[NewsItem] | None = None,
) -> DailyRunResult:
    if len(bars) < 2:
        raise ValueError("at least two bars are required to execute a signal")
    spec = market or JAPAN
    stored = store.load_portfolio()
    account_created = stored is None
    portfolio = stored or Portfolio(initial_cash)
    last_processed = store.last_processed_date()

    result = run_engine(
        bars=bars,
        strategy=strategy,
        portfolio=portfolio,
        risk=RiskManager(risk_config, spec),
        broker=SimulatedBroker(spec, slippage_rate),
        store=store,
        news=news,
        execute_after=last_processed,
    )

    for trade in result.trades:
        store.record_trade(trade)
    for decision in result.decisions:
        store.record_equity(decision.date, decision.equity, decision.cash)
    if result.pending_signal is not None:
        store.record_proposal(result.pending_signal)

    processed = tuple(decision.date for decision in result.decisions)
    latest = processed[-1] if processed else last_processed
    store.save_portfolio(portfolio, latest)
    store.commit()

    last_close = bars[-1].close
    return DailyRunResult(
        account=store.account,
        account_created=account_created,
        processed_dates=processed,
        trades=result.trades,
        decisions=result.decisions,
        positions=tuple(portfolio.positions.values()),
        cash=portfolio.cash,
        equity=portfolio.equity({bars[-1].symbol: last_close}),
        last_processed_date=latest,
        pending_signal=result.pending_signal,
    )
