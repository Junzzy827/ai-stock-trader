"""The single evaluation loop shared by backtesting and paper trading.

Signals are computed at a bar's close and executed at the next bar's open, so
there is no look-ahead. Swapping the bars fed in (full history vs. the latest
window) and the store written to is the only difference between a backtest and
a daily run; the decision path itself is identical, so research results and
live behaviour cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

from ..domain.models import BUY, Decision, Fill, NewsItem, OHLCV, SELL, Signal, Trade
from ..domain.portfolio import Portfolio
from ..domain.risk import RiskManager
from ..domain.strategy import TechnicalNewsStrategy
from ..ports import Broker, DecisionStore


@dataclass(frozen=True)
class EngineResult:
    portfolio: Portfolio
    signals: tuple[Signal, ...]
    trades: tuple[Trade, ...]
    decisions: tuple[Decision, ...]
    equity_curve: tuple[tuple[Date, float], ...]
    pending_signal: Signal | None


def run_engine(
    bars: list[OHLCV],
    strategy: TechnicalNewsStrategy,
    portfolio: Portfolio,
    risk: RiskManager,
    broker: Broker,
    store: DecisionStore | None = None,
    news: list[NewsItem] | None = None,
) -> EngineResult:
    if not bars:
        return EngineResult(portfolio, (), (), (), (), None)
    signals = strategy.generate(bars, news)
    trades: list[Trade] = []
    decisions: list[Decision] = []
    equity_curve: list[tuple[Date, float]] = [(bars[0].date, portfolio.cash)]

    for index in range(1, len(bars)):
        signal = signals[index - 1]
        reference = bars[index - 1]
        bar = bars[index]
        reference_prices = {bar.symbol: reference.close}

        orders = risk.protective_orders(portfolio, bar.date)
        stop_fills = broker.execute(orders, bar, portfolio)
        for fill in stop_fills:
            trades.append(_as_trade(fill, portfolio))
        note = "stopped out" if stop_fills else ""

        if not stop_fills:
            entry_orders = risk.plan(signal, portfolio, reference_prices, bar.date)
            orders = [*orders, *entry_orders]
            fills = broker.execute(entry_orders, bar, portfolio)
            for fill in fills:
                trades.append(_as_trade(fill, portfolio))
            if entry_orders and not fills:
                note = "order not filled"
            elif signal.action in (BUY, SELL) and not entry_orders:
                note = _skip_reason(signal, portfolio)
            all_fills = tuple(fills)
        else:
            all_fills = ()

        risk.update_stops(portfolio, {bar.symbol: bar.close})
        equity = portfolio.equity({bar.symbol: bar.close})
        equity_curve.append((bar.date, equity))
        position = portfolio.position(bar.symbol)
        decision = Decision(
            date=bar.date,
            symbol=bar.symbol,
            action=signal.action,
            score=signal.score,
            reason=signal.reason,
            technical_score=signal.technical_score,
            news_score=signal.news_score,
            orders=tuple(orders),
            fills=tuple([*stop_fills, *all_fills]),
            position_quantity=position.quantity if position else 0,
            position_avg_price=position.avg_price if position else 0.0,
            stop_price=position.stop_price if position else None,
            cash=portfolio.cash,
            equity=equity,
            note=note,
        )
        decisions.append(decision)
        if store is not None:
            store.record(decision)

    return EngineResult(
        portfolio=portfolio,
        signals=tuple(signals),
        trades=tuple(trades),
        decisions=tuple(decisions),
        equity_curve=tuple(equity_curve),
        pending_signal=signals[-1] if signals else None,
    )


def _as_trade(fill: Fill, portfolio: Portfolio) -> Trade:
    realized = portfolio.apply(fill)
    return Trade(
        date=fill.date,
        symbol=fill.symbol,
        action=fill.side,
        quantity=fill.quantity,
        price=fill.price,
        commission=fill.commission,
        cash_after=portfolio.cash,
        realized_pnl=realized,
        reason=fill.reason,
    )


def _skip_reason(signal: Signal, portfolio: Portfolio) -> str:
    held = portfolio.quantity(signal.symbol)
    if signal.action == BUY and held > 0:
        return "already holding"
    if signal.action == SELL and held == 0:
        return "nothing to sell"
    if signal.action == BUY:
        return "insufficient cash for one lot"
    return ""
