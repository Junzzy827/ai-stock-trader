from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

from ...domain.models import NewsItem


def _published_date(raw: str | None, fallback: date) -> date:
    """RSS timestamps vary; fall back to the fetch date rather than dropping."""
    if not raw:
        return fallback
    try:
        parsed = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return fallback
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.date()


def fetch_rss_news(url: str, timeout: int = 15) -> list[NewsItem]:
    """Fetch a common RSS 2.0 feed without adding a runtime dependency.

    ``fetched_at`` is stamped separately from ``published_at`` so a stored
    archive can tell "when we learned this" from "when it happened".
    """
    request = Request(url, headers={"User-Agent": "ai-stock-trader/0.1"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is user-configured
        root = ET.fromstring(response.read())
    fetched_at = date.today()
    items: list[NewsItem] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        key = link or title
        if not key or key in seen:
            continue
        seen.add(key)
        published = _published_date(item.findtext("pubDate"), fetched_at)
        items.append(NewsItem(published, title, summary, link, (), fetched_at))
    return items
