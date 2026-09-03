"""The single evaluation loop shared by backtesting and paper trading.

Signals are computed at a bar's close and executed at the next bar's open, so
there is no look-ahead. Swapping the bars fed in (full history vs. the latest
window) and the store written to is the only difference between a backtest and
a daily run; the decision path itself is identical, so research results and
live behaviour cannot drift apart.

Within one date the order is fixed: protective stops, then exits, then entries
ranked by signal score. Exits run before entries so the cash they release is
available the same day, and ranking entries makes the outcome independent of
how the symbols happened to be ordered when several compete for the same cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

from ..domain.models import BUY, Decision, Fill, NewsItem, SELL, Signal, Trade
from ..domain.portfolio import Portfolio
from ..domain.risk import RiskManager
from ..domain.strategy import TechnicalNewsStrategy
from ..domain.universe import Universe
from ..ports import Broker, DecisionStore


@dataclass(frozen=True)
class EngineResult:
    portfolio: Portfolio
    signals: dict[str, tuple[Signal, ...]]
    trades: tuple[Trade, ...]
    decisions: tuple[Decision, ...]
    equity_curve: tuple[tuple[Date, float], ...]
    pending_signals: tuple[Signal, ...]

    @property
    def processed_dates(self) -> tuple[Date, ...]:
        seen: dict[Date, None] = {}
        for decision in self.decisions:
            seen.setdefault(decision.date, None)
        return tuple(seen)


def run_engine(
    universe: Universe,
    strategy: TechnicalNewsStrategy,
    portfolio: Portfolio,
    risk: RiskManager,
    broker: Broker,
    store: DecisionStore | None = None,
    news: list[NewsItem] | None = None,
    execute_after: Date | None = None,
) -> EngineResult:
    """Evaluate the universe, executing only dates after ``execute_after``.

    Earlier bars are still fed to the strategy so indicators keep their warm-up
    history; they simply are not traded again. That is what lets a daily run
    resume from a stored portfolio instead of replaying the whole history.
    """
    if universe.is_empty():
        return EngineResult(portfolio, {}, (), (), (), ())

    signals = {symbol: tuple(strategy.generate(list(universe.bars(symbol)), news)) for symbol in universe.symbols}
    pending = tuple(series[-1] for series in signals.values() if series)

    timeline = universe.timeline
    executable = [
        (position, day)
        for position, day in enumerate(timeline)
        if position > 0 and (execute_after is None or day > execute_after)
    ]
    if not executable:
        return EngineResult(portfolio, signals, (), (), (), pending)

    # A position whose symbol left the universe still has to be valued: fall
    # back to its cost so equity stays defined. The caller reports it as stale.
    last_close: dict[str, float] = {
        symbol: position.avg_price for symbol, position in portfolio.positions.items()
    }
    for day in timeline[: executable[0][0]]:
        for symbol in universe.symbols:
            bar = universe.bar_at(symbol, day)
            if bar is not None:
                last_close[symbol] = bar.close

    trades: list[Trade] = []
    decisions: list[Decision] = []
    equity_curve: list[tuple[Date, float]] = [
        (timeline[executable[0][0] - 1], portfolio.equity(_prices_for(portfolio, last_close)))
    ]

    for _, day in executable:
        day_trades, day_decisions = _process_day(
            day, universe, signals, portfolio, risk, broker, last_close
        )
        trades.extend(day_trades)
        for decision in day_decisions:
            decisions.append(decision)
            if store is not None:
                store.record(decision)
        equity_curve.append((day, portfolio.equity(_prices_for(portfolio, last_close))))

    return EngineResult(
        portfolio=portfolio,
        signals=signals,
        trades=tuple(trades),
        decisions=tuple(decisions),
        equity_curve=tuple(equity_curve),
        pending_signals=pending,
    )


def _process_day(
    day: Date,
    universe: Universe,
    signals: dict[str, tuple[Signal, ...]],
    portfolio: Portfolio,
    risk: RiskManager,
    broker: Broker,
    last_close: dict[str, float],
) -> tuple[list[Trade], list[Decision]]:
    tradable = []
    for symbol in universe.symbols:
        position = universe.position_of(symbol, day)
        if position is None or position == 0:
            continue
        tradable.append((symbol, universe.bars(symbol)[position], signals[symbol][position - 1]))
    if not tradable:
        return [], []

    reference_prices = dict(last_close)
    trades: list[Trade] = []
    orders_by_symbol: dict[str, list] = {symbol: [] for symbol, _, _ in tradable}
    fills_by_symbol: dict[str, list] = {symbol: [] for symbol, _, _ in tradable}
    notes: dict[str, str] = {symbol: "" for symbol, _, _ in tradable}

    # 1. Standing stops, placed before the bar trades.
    standing: dict[str, list] = {}
    for order in risk.protective_orders(portfolio, day):
        standing.setdefault(order.symbol, []).append(order)
    for symbol, bar, _ in tradable:
        stop_orders = standing.get(symbol, [])
        if not stop_orders:
            continue
        orders_by_symbol[symbol].extend(stop_orders)
        stop_fills = broker.execute(stop_orders, bar, portfolio)
        for fill in stop_fills:
            trades.append(_as_trade(fill, portfolio))
        fills_by_symbol[symbol].extend(stop_fills)
        if stop_fills:
            notes[symbol] = "stopped out"

    # 2. Exits first, then entries ranked by conviction, so freed cash is reusable.
    exits = [item for item in tradable if item[2].action == SELL]
    entries = sorted(
        (item for item in tradable if item[2].action == BUY),
        key=lambda item: item[2].score,
        reverse=True,
    )
    for symbol, bar, signal in [*exits, *entries]:
        if notes[symbol] == "stopped out":
            continue
        orders = risk.plan(signal, portfolio, reference_prices, day)
        if not orders:
            notes[symbol] = _skip_reason(signal, portfolio, risk)
            continue
        orders_by_symbol[symbol].extend(orders)
        fills = broker.execute(orders, bar, portfolio)
        for fill in fills:
            trades.append(_as_trade(fill, portfolio))
        fills_by_symbol[symbol].extend(fills)
        if not fills:
            notes[symbol] = "order not filled"

    # 3. Mark to the close, ratchet stops, then record one decision per symbol.
    closes = {symbol: bar.close for symbol, bar, _ in tradable}
    last_close.update(closes)
    risk.update_stops(portfolio, closes)
    equity = portfolio.equity(_prices_for(portfolio, last_close))

    decisions = []
    for symbol, _, signal in tradable:
        position = portfolio.position(symbol)
        decisions.append(
            Decision(
                date=day,
                symbol=symbol,
                action=signal.action,
                score=signal.score,
                reason=signal.reason,
                technical_score=signal.technical_score,
                news_score=signal.news_score,
                orders=tuple(orders_by_symbol[symbol]),
                fills=tuple(fills_by_symbol[symbol]),
                position_quantity=position.quantity if position else 0,
                position_avg_price=position.avg_price if position else 0.0,
                stop_price=position.stop_price if position else None,
                cash=portfolio.cash,
                equity=equity,
                note=notes[symbol],
            )
        )
    return trades, decisions


def _prices_for(portfolio: Portfolio, last_close: dict[str, float]) -> dict[str, float]:
    """Carry the last known close forward for symbols that did not trade."""
    return {symbol: last_close[symbol] for symbol in portfolio.positions}


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


def _skip_reason(signal: Signal, portfolio: Portfolio, risk: RiskManager) -> str:
    held = portfolio.quantity(signal.symbol)
    if signal.action == BUY and held > 0:
        return "already holding"
    if signal.action == SELL and held == 0:
        return "nothing to sell"
    if signal.action == BUY:
        if len(portfolio.positions) >= risk.config.max_positions:
            return "position limit reached"
        return "insufficient cash for one lot"
    return ""
