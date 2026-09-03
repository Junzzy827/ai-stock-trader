"""SQLite-backed state and decision history.

An account's cash, positions and armed stops survive process restarts, so a
daily run resumes where the previous one stopped instead of replaying the
whole history. Writes stay in one transaction until ``commit`` so an
interrupted run leaves the stored ``last_processed_date`` unadvanced and the
next run simply redoes that day.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ...domain.models import Decision, Fill, Order, Signal, Trade
from ...domain.portfolio import Portfolio, Position

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    account TEXT PRIMARY KEY,
    initial_cash REAL NOT NULL,
    cash REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    total_commission REAL NOT NULL DEFAULT 0,
    last_processed_date TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_price REAL NOT NULL,
    stop_price REAL,
    peak_price REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (account, symbol)
);
CREATE TABLE IF NOT EXISTS decisions (
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    score REAL NOT NULL,
    reason TEXT NOT NULL,
    technical_score REAL NOT NULL,
    news_score REAL NOT NULL,
    orders TEXT NOT NULL,
    fills TEXT NOT NULL,
    position_quantity INTEGER NOT NULL,
    position_avg_price REAL NOT NULL,
    stop_price REAL,
    cash REAL NOT NULL,
    equity REAL NOT NULL,
    note TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (account, date, symbol)
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    commission REAL NOT NULL,
    cash_after REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (account, date, symbol, action, quantity, price)
);
CREATE TABLE IF NOT EXISTS equity_history (
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    PRIMARY KEY (account, date)
);
CREATE TABLE IF NOT EXISTS proposals (
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    score REAL NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    decided_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (account, date, symbol)
);
CREATE INDEX IF NOT EXISTS decisions_by_date ON decisions (account, date);
CREATE INDEX IF NOT EXISTS trades_by_date ON trades (account, date);
"""

PROPOSED = "PROPOSED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class SqliteStore:
    """Account-scoped store. Use one instance per account."""

    def __init__(self, path: str | Path, account: str = "default"):
        self.path = Path(path)
        self.account = account
        if self.path.parent != Path(""):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)
        self._connection.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._connection.commit()

    # --- lifecycle -----------------------------------------------------
    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SqliteStore":
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        if exc_type is not None:
            self.rollback()
        self.close()

    # --- account state -------------------------------------------------
    def load_portfolio(self) -> Portfolio | None:
        row = self._connection.execute(
            "SELECT * FROM accounts WHERE account = ?", (self.account,)
        ).fetchone()
        if row is None:
            return None
        portfolio = Portfolio(row["initial_cash"])
        portfolio.cash = row["cash"]
        portfolio.realized_pnl = row["realized_pnl"]
        portfolio.total_commission = row["total_commission"]
        for position_row in self._connection.execute(
            "SELECT * FROM positions WHERE account = ?", (self.account,)
        ):
            portfolio.positions[position_row["symbol"]] = Position(
                symbol=position_row["symbol"],
                quantity=position_row["quantity"],
                avg_price=position_row["avg_price"],
                stop_price=position_row["stop_price"],
                peak_price=position_row["peak_price"],
            )
        return portfolio

    def save_portfolio(self, portfolio: Portfolio, last_processed: date | None) -> None:
        self._connection.execute(
            """
            INSERT INTO accounts
                (account, initial_cash, cash, realized_pnl, total_commission, last_processed_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account) DO UPDATE SET
                cash = excluded.cash,
                realized_pnl = excluded.realized_pnl,
                total_commission = excluded.total_commission,
                last_processed_date = excluded.last_processed_date,
                updated_at = excluded.updated_at
            """,
            (
                self.account,
                portfolio.initial_cash,
                portfolio.cash,
                portfolio.realized_pnl,
                portfolio.total_commission,
                last_processed.isoformat() if last_processed else None,
                _now(),
            ),
        )
        self._connection.execute("DELETE FROM positions WHERE account = ?", (self.account,))
        self._connection.executemany(
            "INSERT INTO positions (account, symbol, quantity, avg_price, stop_price, peak_price)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (self.account, p.symbol, p.quantity, p.avg_price, p.stop_price, p.peak_price)
                for p in portfolio.positions.values()
            ],
        )

    def last_processed_date(self) -> date | None:
        row = self._connection.execute(
            "SELECT last_processed_date FROM accounts WHERE account = ?", (self.account,)
        ).fetchone()
        return _as_date(row["last_processed_date"]) if row else None

    # --- history -------------------------------------------------------
    def record(self, decision: Decision) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO decisions
                (account, date, symbol, action, score, reason, technical_score, news_score,
                 orders, fills, position_quantity, position_avg_price, stop_price, cash,
                 equity, note, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.account,
                decision.date.isoformat(),
                decision.symbol,
                decision.action,
                decision.score,
                decision.reason,
                decision.technical_score,
                decision.news_score,
                _dump([order.to_dict() for order in decision.orders]),
                _dump([fill.to_dict() for fill in decision.fills]),
                decision.position_quantity,
                decision.position_avg_price,
                decision.stop_price,
                decision.cash,
                decision.equity,
                decision.note,
                _now(),
            ),
        )

    def record_trade(self, trade: Trade) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO trades
                (account, date, symbol, action, quantity, price, commission,
                 cash_after, realized_pnl, reason, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.account,
                trade.date.isoformat(),
                trade.symbol,
                trade.action,
                trade.quantity,
                trade.price,
                trade.commission,
                trade.cash_after,
                trade.realized_pnl,
                trade.reason,
                _now(),
            ),
        )

    def record_equity(self, day: date, equity: float, cash: float) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO equity_history (account, date, equity, cash) VALUES (?, ?, ?, ?)",
            (self.account, day.isoformat(), equity, cash),
        )

    def record_proposal(self, signal: Signal, status: str = PROPOSED) -> None:
        """Store the next session's candidate so a human can act on it."""
        self._connection.execute(
            """
            INSERT INTO proposals (account, date, symbol, action, score, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account, date, symbol) DO UPDATE SET
                action = excluded.action,
                score = excluded.score,
                reason = excluded.reason
            """,
            (
                self.account,
                signal.date.isoformat(),
                signal.symbol,
                signal.action,
                signal.score,
                signal.reason,
                status,
            ),
        )

    def decide_proposal(self, day: date, symbol: str, status: str, note: str = "") -> bool:
        """Record a human APPROVED/REJECTED verdict. Returns whether a row matched."""
        if status not in (APPROVED, REJECTED):
            raise ValueError("status must be APPROVED or REJECTED")
        cursor = self._connection.execute(
            "UPDATE proposals SET status = ?, decided_at = ?, note = ?"
            " WHERE account = ? AND date = ? AND symbol = ?",
            (status, _now(), note, self.account, day.isoformat(), symbol),
        )
        return cursor.rowcount > 0

    # --- queries -------------------------------------------------------
    def pending_proposals(self) -> list[dict[str, Any]]:
        """Every proposal from the most recent proposal date, one per symbol."""
        rows = self._connection.execute(
            "SELECT * FROM proposals WHERE account = ? AND date = "
            "(SELECT MAX(date) FROM proposals WHERE account = ?) ORDER BY symbol",
            (self.account, self.account),
        )
        return [dict(row) for row in rows]

    def equity_curve(self) -> list[tuple[date, float]]:
        return [
            (date.fromisoformat(row["date"]), row["equity"])
            for row in self._connection.execute(
                "SELECT date, equity FROM equity_history WHERE account = ? ORDER BY date",
                (self.account,),
            )
        ]

    def trades(self) -> list[Trade]:
        return [
            Trade(
                date=date.fromisoformat(row["date"]),
                symbol=row["symbol"],
                action=row["action"],
                quantity=row["quantity"],
                price=row["price"],
                commission=row["commission"],
                cash_after=row["cash_after"],
                realized_pnl=row["realized_pnl"],
                reason=row["reason"],
            )
            for row in self._connection.execute(
                "SELECT * FROM trades WHERE account = ? ORDER BY date, id", (self.account,)
            )
        ]

    def decisions(self, limit: int | None = None) -> list[Decision]:
        query = "SELECT * FROM decisions WHERE account = ? ORDER BY date DESC"
        parameters: tuple[Any, ...] = (self.account,)
        if limit is not None:
            query += " LIMIT ?"
            parameters += (limit,)
        rows = list(self._connection.execute(query, parameters))
        return [_decision_from_row(row) for row in reversed(rows)]


def _dump(payload: Iterable[dict[str, Any]]) -> str:
    return json.dumps(list(payload), ensure_ascii=False, default=str)


def _decision_from_row(row: sqlite3.Row) -> Decision:
    return Decision(
        date=date.fromisoformat(row["date"]),
        symbol=row["symbol"],
        action=row["action"],
        score=row["score"],
        reason=row["reason"],
        technical_score=row["technical_score"],
        news_score=row["news_score"],
        orders=tuple(Order(**_revive_dates(item)) for item in json.loads(row["orders"])),
        fills=tuple(Fill(**_revive_dates(item)) for item in json.loads(row["fills"])),
        position_quantity=row["position_quantity"],
        position_avg_price=row["position_avg_price"],
        stop_price=row["stop_price"],
        cash=row["cash"],
        equity=row["equity"],
        note=row["note"],
    )


def _revive_dates(payload: dict[str, Any]) -> dict[str, Any]:
    revived = dict(payload)
    if isinstance(revived.get("date"), str):
        revived["date"] = date.fromisoformat(revived["date"])
    return revived
