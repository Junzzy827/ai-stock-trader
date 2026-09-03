"""Deterministic, offline news scoring.

Keyword scoring is pure logic, so it lives in the core; anything that calls out
to a network (Claude, RSS) is an adapter implementing the same port.

News is scored with a decay window rather than an exact-date match: a
headline from two days ago still carries weight today, just less of it. This
also makes market-wide items (``symbols`` empty) apply to every symbol
instead of none.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import NewsItem

WeightedItem = tuple[NewsItem, float]


class KeywordNewsAnalyzer:
    """Transparent baseline used by tests and offline runs."""

    POSITIVE = ("増益", "上方修正", "成長", "受注", "positive", "upgrade", "beat", "growth")
    NEGATIVE = ("減益", "下方修正", "赤字", "不正", "negative", "downgrade", "miss", "loss")

    def score(self, items: Iterable[WeightedItem]) -> tuple[float, str]:
        positive = 0.0
        negative = 0.0
        for item, weight in items:
            headline = f"{item.title} {item.summary}".lower()
            positive += weight * sum(word.lower() in headline for word in self.POSITIVE)
            negative += weight * sum(word.lower() in headline for word in self.NEGATIVE)
        raw = positive - negative
        score = max(-1.0, min(1.0, raw / 3))
        return score, f"news keywords: +{positive:.1f}/-{negative:.1f}"


def dedupe(items: Iterable[NewsItem]) -> list[NewsItem]:
    """Keep the first occurrence of each ``dedup_key`` (same URL, or same
    title on the same day from a feed with no link)."""
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in items:
        key = item.dedup_key
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def decay_weight(published_at: date, as_of: date, decay_rate: float) -> float:
    days_old = (as_of - published_at).days
    if days_old < 0:
        return 0.0  # not yet published as of this bar: never look ahead
    return decay_rate**days_old


def relevant_weighted_items(
    items: Iterable[NewsItem],
    symbol: str,
    as_of: date,
    window_days: int,
    decay_rate: float,
) -> list[WeightedItem]:
    """Items about ``symbol`` (or market-wide) published within the window
    ending at ``as_of``, each paired with its decay weight."""
    weighted = []
    for item in items:
        if not item.is_relevant_to(symbol):
            continue
        age = (as_of - item.published_at).days
        if not 0 <= age <= window_days:
            continue
        weighted.append((item, decay_weight(item.published_at, as_of, decay_rate)))
    return weighted
