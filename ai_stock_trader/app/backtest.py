from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Any, Iterable, Mapping

from ..adapters.broker.simulated import SimulatedBroker
from ..domain.market import JAPAN, MarketSpec
from ..domain.metrics import PerformanceMetrics, compute
from ..domain.models import Decision, NewsItem, OHLCV, Signal, Trade
from ..domain.portfolio import Portfolio
from ..domain.risk import RiskConfig, RiskManager
from ..domain.strategy import TechnicalNewsStrategy
from ..domain.universe import Universe
from ..ports import DecisionStore
from .engine import run_engine

PriceData = Universe | Mapping[str, Iterable[OHLCV]] | Iterable[OHLCV]


@dataclass(frozen=True)
class BacktestResult:
    initial_cash: float
    final_cash: float
    final_equity: float
    metrics: PerformanceMetrics
    trades: tuple[Trade, ...]
    signals: dict[str, tuple[Signal, ...]]
    decisions: tuple[Decision, ...]
    equity_curve: tuple[tuple[Date, float], ...]
    pending_signals: tuple[Signal, ...]

    @property
    def return_rate(self) -> float:
        return self.metrics.return_rate

    @property
    def buy_and_hold_return_rate(self) -> float | None:
        return self.metrics.buy_and_hold_return_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_cash": self.initial_cash,
            "final_cash": self.final_cash,
            "final_equity": self.final_equity,
            "metrics": self.metrics.to_dict(),
            "trades": [trade.to_dict() for trade in self.trades],
            "signals": {
                symbol: [signal.to_dict() for signal in series]
                for symbol, series in self.signals.items()
            },
            "equity_curve": [{"date": day, "equity": equity} for day, equity in self.equity_curve],
            "pending_signals": [signal.to_dict() for signal in self.pending_signals],
        }


def run_backtest(
    data: PriceData,
    strategy: TechnicalNewsStrategy,
    initial_cash: float = 1_000_000,
    commission_rate: float = 0.001,
    news: list[NewsItem] | None = None,
    *,
    risk_config: RiskConfig | None = None,
    market: MarketSpec | None = None,
    slippage_rate: float = 0.0,
    store: DecisionStore | None = None,
) -> BacktestResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    universe = Universe.of(data)
    spec = _market_spec(market, commission_rate)
    portfolio = Portfolio(initial_cash)
    if universe.is_empty():
        empty = compute((), (), initial_cash, None, 0.0)
        return BacktestResult(initial_cash, initial_cash, initial_cash, empty, (), {}, (), (), ())

    result = run_engine(
        universe=universe,
        strategy=strategy,
        portfolio=portfolio,
        risk=RiskManager(risk_config, spec),
        broker=SimulatedBroker(spec, slippage_rate),
        store=store,
        news=news,
    )
    final_equity = result.equity_curve[-1][1] if result.equity_curve else initial_cash
    metrics = compute(
        result.equity_curve,
        result.trades,
        initial_cash,
        buy_and_hold_return_rate(universe),
        portfolio.total_commission,
    )
    return BacktestResult(
        initial_cash=initial_cash,
        final_cash=portfolio.cash,
        final_equity=final_equity,
        metrics=metrics,
        trades=result.trades,
        signals=result.signals,
        decisions=result.decisions,
        equity_curve=result.equity_curve,
        pending_signals=result.pending_signals,
    )


def buy_and_hold_return_rate(universe: Universe) -> float | None:
    """Equal-weighted buy at each symbol's first open, held to its last close."""
    returns = []
    for symbol in universe.symbols:
        bars = universe.bars(symbol)
        if bars[0].open > 0:
            returns.append(bars[-1].close / bars[0].open - 1)
    return sum(returns) / len(returns) if returns else None


def _market_spec(market: MarketSpec | None, commission_rate: float) -> MarketSpec:
    """The CLI passes a commission rate; a caller may pass a full spec instead."""
    base = market or JAPAN
    if market is not None and commission_rate == base.commission_rate:
        return base
    return MarketSpec(
        name=base.name,
        currency=base.currency,
        lot_size=base.lot_size,
        commission_rate=commission_rate,
        min_commission=base.min_commission,
    )
