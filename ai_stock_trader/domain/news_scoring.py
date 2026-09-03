"""Deterministic, offline news scoring.

Keyword scoring is pure logic, so it lives in the core; anything that calls out
to a network (Claude, RSS) is an adapter implementing the same port.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import NewsItem


class KeywordNewsAnalyzer:
    """Transparent baseline used by tests and offline runs."""

    POSITIVE = ("増益", "上方修正", "成長", "受注", "positive", "upgrade", "beat", "growth")
    NEGATIVE = ("減益", "下方修正", "赤字", "不正", "negative", "downgrade", "miss", "loss")

    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]:
        headlines = [f"{item.title} {item.summary}".lower() for item in items]
        positive = sum(sum(word.lower() in headline for word in self.POSITIVE) for headline in headlines)
        negative = sum(sum(word.lower() in headline for word in self.NEGATIVE) for headline in headlines)
        raw = positive - negative
        score = max(-1.0, min(1.0, raw / 3))
        return score, f"news keywords: +{positive}/-{negative}"


def news_by_date(items: Iterable[NewsItem]) -> dict[date, list[NewsItem]]:
    grouped: dict[date, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.published_at, []).append(item)
    return grouped
