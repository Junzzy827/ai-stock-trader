from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from ...domain.models import OHLCV
from ...domain.universe import Universe


class CsvPriceDataSource:
    """Load normalized OHLCV CSV data.

    Required columns: date, open, high, low, close. ``symbol`` and ``volume``
    are optional. Dates use YYYY-MM-DD. One file may hold many symbols.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _rows(self) -> Iterable[tuple[str | None, dict[str, str]]]:
        with self.path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                yield (row.get("symbol") or None), row

    def symbols(self) -> list[str]:
        return sorted({symbol for symbol, _ in self._rows() if symbol})

    def prices(self, symbol: str) -> list[OHLCV]:
        rows = [
            _to_bar(row, row_symbol or symbol)
            for row_symbol, row in self._rows()
            if row_symbol is None or row_symbol == symbol
        ]
        return sorted(rows, key=lambda bar: bar.date)

    def universe(self, symbols: Iterable[str] | None = None) -> Universe:
        available = self.symbols()
        names = list(symbols) if symbols is not None else available
        if not names:
            raise ValueError(f"{self.path} has no symbol column; pass the symbols explicitly")
        if not available and len(names) > 1:
            raise ValueError(f"{self.path} has no symbol column, so it cannot hold {len(names)} symbols")
        missing = [name for name in names if available and name not in available]
        if missing:
            raise ValueError(f"{self.path} has no rows for {', '.join(missing)}")
        return Universe({name: tuple(self.prices(name)) for name in names})


def _to_bar(row: dict[str, str], symbol: str) -> OHLCV:
    return OHLCV(
        date=date.fromisoformat(row["date"]),
        symbol=symbol,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume") or 0),
    )
