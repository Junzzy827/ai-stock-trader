from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable, Protocol
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .models import NewsItem, OHLCV


class PriceDataSource(Protocol):
    def prices(self, symbol: str) -> list[OHLCV]: ...


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


def fetch_rss_news(url: str, timeout: int = 15) -> list[NewsItem]:
    """Fetch a common RSS 2.0 feed without adding a runtime dependency."""
    request = Request(url, headers={"User-Agent": "ai-stock-trader/0.1"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is user-configured
        root = ET.fromstring(response.read())
    items: list[NewsItem] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        # RSS dates vary widely; retaining the fetch date is less misleading
        # than silently dropping an otherwise useful headline.
        items.append(NewsItem(date.today(), title, summary, link))
    return items


def news_for_date(items: Iterable[NewsItem], target: date) -> list[NewsItem]:
    return [item for item in items if item.published_at <= target]
