"""Read-only account view: what is held, what happened, what is proposed.

The CLI renders this today and a dashboard will render the same structure
later, so the presentation layer never queries the store directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Any

from ..adapters.store.sqlite import SqliteStore
from ..domain.metrics import PerformanceMetrics, compute
from ..domain.models import Decision


@dataclass(frozen=True)
class AccountStatus:
    account: str
    exists: bool
    initial_cash: float
    cash: float
    equity: float
    last_processed_date: Date | None
    positions: tuple[dict[str, Any], ...]
    pending_proposal: dict[str, Any] | None
    recent_decisions: tuple[Decision, ...]
    metrics: PerformanceMetrics | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "exists": self.exists,
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "equity": self.equity,
            "last_processed_date": self.last_processed_date.isoformat() if self.last_processed_date else None,
            "positions": list(self.positions),
            "pending_proposal": self.pending_proposal,
            "recent_decisions": [decision.to_dict() for decision in self.recent_decisions],
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


def account_status(store: SqliteStore, recent: int = 10) -> AccountStatus:
    portfolio = store.load_portfolio()
    if portfolio is None:
        return AccountStatus(store.account, False, 0.0, 0.0, 0.0, None, (), None, (), None)

    equity_curve = store.equity_curve()
    equity = equity_curve[-1][1] if equity_curve else portfolio.cash
    trades = store.trades()
    metrics = (
        compute(equity_curve, trades, portfolio.initial_cash, None, portfolio.total_commission)
        if equity_curve
        else None
    )
    positions = tuple(
        {
            "symbol": position.symbol,
            "quantity": position.quantity,
            "avg_price": position.avg_price,
            "stop_price": position.stop_price,
        }
        for position in portfolio.positions.values()
    )
    return AccountStatus(
        account=store.account,
        exists=True,
        initial_cash=portfolio.initial_cash,
        cash=portfolio.cash,
        equity=equity,
        last_processed_date=store.last_processed_date(),
        positions=positions,
        pending_proposal=store.latest_proposal(),
        recent_decisions=tuple(store.decisions(limit=recent)),
        metrics=metrics,
    )
