from __future__ import annotations

from .models import BacktestResult, NewsItem, OHLCV, Signal, Trade
from .strategy import TechnicalNewsStrategy


def run_backtest(
    bars: list[OHLCV],
    strategy: TechnicalNewsStrategy,
    initial_cash: float = 100_000,
    commission_rate: float = 0.001,
    news: list[NewsItem] | None = None,
) -> BacktestResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if not bars:
        return BacktestResult(initial_cash, initial_cash, initial_cash, 0.0, 0.0, (), ())
    signals = strategy.generate(bars, news)
    cash = initial_cash
    quantity = 0
    trades: list[Trade] = []
    for index in range(1, len(bars)):
        signal = signals[index - 1]
        execution_bar = bars[index]
        if signal.action == "BUY" and quantity == 0:
            buy_quantity = int(cash / (execution_bar.open * (1 + commission_rate)))
            if buy_quantity > 0:
                cost = buy_quantity * execution_bar.open
                cash -= cost * (1 + commission_rate)
                quantity = buy_quantity
                trades.append(Trade(execution_bar.date, execution_bar.symbol, "BUY", quantity, execution_bar.open, cash, signal.reason))
        elif signal.action == "SELL" and quantity > 0:
            proceeds = quantity * execution_bar.open
            cash += proceeds * (1 - commission_rate)
            trades.append(Trade(execution_bar.date, execution_bar.symbol, "SELL", quantity, execution_bar.open, cash, signal.reason))
            quantity = 0
    final_equity = cash + quantity * bars[-1].close
    buy_and_hold = initial_cash * (bars[-1].close / bars[0].open)
    return BacktestResult(
        initial_cash=initial_cash,
        final_cash=cash,
        final_equity=final_equity,
        return_rate=final_equity / initial_cash - 1,
        buy_and_hold_return_rate=buy_and_hold / initial_cash - 1,
        trades=tuple(trades),
        signals=tuple(signals),
    )
