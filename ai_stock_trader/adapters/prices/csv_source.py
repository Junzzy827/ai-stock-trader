from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ...domain.models import OHLCV


class CsvPriceDataSource:
    """Load normalized OHLCV CSV data.

    Required columns: date, open, high, low, close. ``symbol`` and ``volume``
    are optional. Dates use YYYY-MM-DD.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def prices(self, symbol: str) -> list[OHLCV]:
        rows: list[OHLCV] = []
        with self.path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                row_symbol = row.get("symbol") or symbol
                if row_symbol != symbol:
                    continue
                rows.append(
                    OHLCV(
                        date=date.fromisoformat(row["date"]),
                        symbol=row_symbol,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0),
                    )
                )
        return sorted(rows, key=lambda item: item.date)
