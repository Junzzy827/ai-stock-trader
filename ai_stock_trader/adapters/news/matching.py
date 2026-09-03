"""Tags fetched headlines with the symbols they are about.

An RSS feed has no notion of ticker codes, so matching is done here by
substring search against a caller-supplied alias list (company name, ticker,
common abbreviations). An item that matches nothing is left market-wide
(``symbols == ()``), which the decay-window scorer treats as relevant to
every symbol rather than to none.
"""

from __future__ import annotations

from typing import Mapping

from ...domain.models import NewsItem


def tag_symbols(item: NewsItem, aliases: Mapping[str, tuple[str, ...]]) -> NewsItem:
    haystack = f"{item.title} {item.summary}"
    matched = tuple(
        symbol
        for symbol, names in aliases.items()
        if any(name and name in haystack for name in (symbol, *names))
    )
    if not matched:
        return item
    return NewsItem(item.published_at, item.title, item.summary, item.url, matched, item.fetched_at)


def tag_all(items: list[NewsItem], aliases: Mapping[str, tuple[str, ...]]) -> list[NewsItem]:
    if not aliases:
        return items
    return [tag_symbols(item, aliases) for item in items]
