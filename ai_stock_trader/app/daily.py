"""Incremental daily run: the operating entry point for paper trading.

``run_daily`` loads the stored portfolio, evaluates only the dates that
appeared since the last run, and persists the result atomically. It shares
``run_engine`` with the backtester, so a day traded live follows exactly the
path it would have followed in a backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from ..adapters.broker.simulated import SimulatedBroker
from ..domain.market import JAPAN, MarketSpec
from ..domain.models import Decision, NewsItem, Signal, Trade
from ..domain.portfolio import Portfolio, Position
from ..domain.risk import RiskConfig, RiskManager
from ..domain.strategy import TechnicalNewsStrategy
from ..domain.universe import Universe
from ..ports import StateStore
from .backtest import PriceData
from .engine import run_engine


@dataclass(frozen=True)
class DailyRunResult:
    account: str
    account_created: bool
    symbols: tuple[str, ...]
    processed_dates: tuple[Date, ...]
    trades: tuple[Trade, ...]
    decisions: tuple[Decision, ...]
    positions: tuple[Position, ...]
    cash: float
    equity: float
    last_processed_date: Date | None
    pending_signals: tuple[Signal, ...]
    stale_symbols: tuple[str, ...]

    @property
    def up_to_date(self) -> bool:
        return not self.processed_dates

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "account_created": self.account_created,
            "symbols": list(self.symbols),
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
            # The latest bar has no execution bar yet: these are the next session's candidates.
            "pending_signals": [signal.to_dict() for signal in self.pending_signals],
            # Held symbols no longer in the universe; they are marked at cost, not at market.
            "stale_symbols": list(self.stale_symbols),
        }


def run_daily(
    store: StateStore,
    data: PriceData,
    strategy: TechnicalNewsStrategy,
    *,
    initial_cash: float = 1_000_000,
    risk_config: RiskConfig | None = None,
    market: MarketSpec | None = None,
    slippage_rate: float = 0.0,
    news: list[NewsItem] | None = None,
) -> DailyRunResult:
    universe = Universe.of(data)
    if len(universe.timeline) < 2:
        raise ValueError("at least two dates are required to execute a signal")
    spec = market or JAPAN
    stored = store.load_portfolio()
    account_created = stored is None
    portfolio = stored or Portfolio(initial_cash)
    last_processed = store.last_processed_date()

    result = run_engine(
        universe=universe,
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
    for signal in result.pending_signals:
        store.record_proposal(signal)

    processed = result.processed_dates
    latest = processed[-1] if processed else last_processed
    store.save_portfolio(portfolio, latest)
    store.commit()

    marks, stale = _marks(universe, portfolio)
    return DailyRunResult(
        account=store.account,
        account_created=account_created,
        symbols=universe.symbols,
        processed_dates=processed,
        trades=result.trades,
        decisions=result.decisions,
        positions=tuple(portfolio.positions.values()),
        cash=portfolio.cash,
        equity=portfolio.equity(marks),
        last_processed_date=latest,
        pending_signals=result.pending_signals,
        stale_symbols=stale,
    )


def _marks(universe: Universe, portfolio: Portfolio) -> tuple[dict[str, float], tuple[str, ...]]:
    """Mark held positions to the last close, or to cost if the symbol was dropped."""
    marks: dict[str, float] = {}
    stale: list[str] = []
    for symbol, position in portfolio.positions.items():
        if symbol in universe.series:
            marks[symbol] = universe.bars(symbol)[-1].close
        else:
            marks[symbol] = position.avg_price
            stale.append(symbol)
    return marks, tuple(stale)
