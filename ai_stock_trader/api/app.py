"""Read-mostly HTTP API over a trading account's SQLite state.

The only mutation exposed is deciding a pending proposal (approve/reject) —
the human-in-the-loop step the whole system is built around. Everything else
is a thin wrapper over ``app/status.py`` and ``SqliteStore``, which the CLI
already uses, so the dashboard renders exactly what ``ai-stock-trader
status`` reports.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..adapters.store.sqlite import APPROVED, REJECTED, SqliteStore
from ..app.status import account_status

DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


class ProposalDecision(BaseModel):
    account: str = "default"
    date: str
    symbol: str
    status: Literal["APPROVED", "REJECTED"]
    note: str = ""


def create_app(database: str, default_account: str = "default") -> FastAPI:
    app = FastAPI(title="AI Stock Trader")

    @contextmanager
    def open_store(account: str) -> Iterator[SqliteStore]:
        with SqliteStore(database, account) as store:
            yield store

    @app.get("/api/accounts")
    def list_accounts() -> list[str]:
        with open_store(default_account) as store:
            accounts = store.list_accounts()
        return accounts or [default_account]

    @app.get("/api/status")
    def status(account: str = default_account, recent: int = 50) -> dict:
        with open_store(account) as store:
            return account_status(store, recent=recent).to_dict()

    @app.get("/api/equity-curve")
    def equity_curve(account: str = default_account) -> list[dict]:
        with open_store(account) as store:
            curve = store.equity_curve()
        return [{"date": day.isoformat(), "equity": equity} for day, equity in curve]

    @app.get("/api/trades")
    def trades(account: str = default_account, limit: int = 100) -> list[dict]:
        with open_store(account) as store:
            all_trades = store.trades()
        return [trade.to_dict() for trade in all_trades[-limit:]]

    @app.post("/api/proposals/decide")
    def decide_proposal(payload: ProposalDecision) -> dict:
        try:
            proposal_date = date.fromisoformat(payload.date)
        except ValueError as error:
            raise HTTPException(400, f"invalid date: {payload.date}") from error
        with open_store(payload.account) as store:
            matched = store.decide_proposal(proposal_date, payload.symbol, payload.status, payload.note)
            if not matched:
                raise HTTPException(404, f"no proposal for {payload.symbol} on {payload.date}")
            store.commit()
        return {"date": payload.date, "symbol": payload.symbol, "status": payload.status, "note": payload.note}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD_HTML

    return app
