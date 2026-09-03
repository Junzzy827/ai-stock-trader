"""Performance measures. Total return alone hides how much risk was taken."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date as Date
from math import sqrt
from typing import Any, Sequence

from .models import BUY, SELL, Trade

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    return_rate: float
    # None when there is no single instrument to compare against.
    buy_and_hold_return_rate: float | None
    max_drawdown: float
    sharpe_ratio: float | None
    win_rate: float | None
    round_trips: int
    trade_count: int
    total_commission: float
    average_holding_days: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def max_drawdown(equity_curve: Sequence[tuple[Date, float]]) -> float:
    """Largest peak-to-trough decline, as a positive fraction."""
    peak = None
    worst = 0.0
    for _, equity in equity_curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst


def sharpe_ratio(equity_curve: Sequence[tuple[Date, float]], risk_free_rate: float = 0.0) -> float | None:
    """Annualized Sharpe from daily equity. ``None`` when it is not defined."""
    returns: list[float] = []
    for (_, previous), (_, current) in zip(equity_curve, equity_curve[1:]):
        if previous <= 0:
            return None
        returns.append(current / previous - 1)
    if len(returns) < 2:
        return None
    daily_risk_free = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = [value - daily_risk_free for value in returns]
    mean = sum(excess) / len(excess)
    variance = sum((value - mean) ** 2 for value in excess) / (len(excess) - 1)
    if variance <= 0:
        return None
    return (mean / sqrt(variance)) * sqrt(TRADING_DAYS_PER_YEAR)


def round_trips(trades: Sequence[Trade]) -> list[tuple[Trade, Trade]]:
    """Pair each exit with the entry that opened the position."""
    pairs: list[tuple[Trade, Trade]] = []
    open_entries: dict[str, Trade] = {}
    for trade in trades:
        if trade.action == BUY:
            open_entries.setdefault(trade.symbol, trade)
        elif trade.action == SELL:
            entry = open_entries.pop(trade.symbol, None)
            if entry is not None:
                pairs.append((entry, trade))
    return pairs


def compute(
    equity_curve: Sequence[tuple[Date, float]],
    trades: Sequence[Trade],
    initial_cash: float,
    buy_and_hold_return_rate: float | None,
    total_commission: float,
) -> PerformanceMetrics:
    final_equity = equity_curve[-1][1] if equity_curve else initial_cash
    pairs = round_trips(trades)
    wins = sum(1 for _, exit_trade in pairs if exit_trade.realized_pnl > 0)
    holding_days = [(exit_trade.date - entry.date).days for entry, exit_trade in pairs]
    return PerformanceMetrics(
        return_rate=final_equity / initial_cash - 1,
        buy_and_hold_return_rate=buy_and_hold_return_rate,
        max_drawdown=max_drawdown(equity_curve),
        sharpe_ratio=sharpe_ratio(equity_curve),
        win_rate=(wins / len(pairs)) if pairs else None,
        round_trips=len(pairs),
        trade_count=len(trades),
        total_commission=total_commission,
        average_holding_days=(sum(holding_days) / len(holding_days)) if holding_days else None,
    )
