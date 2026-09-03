from __future__ import annotations

import json
import os
from datetime import date
from typing import Iterable, Protocol
from urllib.request import Request, urlopen

from .models import NewsItem


class NewsAnalyzer(Protocol):
    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]: ...


class KeywordNewsAnalyzer:
    """Deterministic baseline used for tests and offline operation.

    This is deliberately transparent; a Claude-backed analyzer can implement
    the same protocol later without changing the strategy or backtester.
    """

    POSITIVE = ("増益", "上方修正", "成長", "受注", "positive", "upgrade", "beat", "growth")
    NEGATIVE = ("減益", "下方修正", "赤字", "不正", "negative", "downgrade", "miss", "loss")

    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]:
        headlines = [f"{item.title} {item.summary}".lower() for item in items]
        positive = sum(sum(word.lower() in headline for word in self.POSITIVE) for headline in headlines)
        negative = sum(sum(word.lower() in headline for word in self.NEGATIVE) for headline in headlines)
        raw = positive - negative
        score = max(-1.0, min(1.0, raw / 3))
        return score, f"news keywords: +{positive}/-{negative}"


class ClaudeNewsAnalyzer:
    """Optional Claude API adapter; never called unless explicitly selected."""

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-haiku-latest"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeNewsAnalyzer")

    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]:
        payload_items = [{"title": item.title, "summary": item.summary, "url": item.url} for item in items]
        prompt = (
            "Evaluate the market impact of these headlines for a single stock. "
            "Return JSON only with score (-1 to 1) and reason (short Japanese text).\n"
            + json.dumps(payload_items, ensure_ascii=False)
        )
        body = json.dumps({"model": self.model, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}).encode()
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed API endpoint
            result = json.loads(response.read())
        text = result["content"][0]["text"]
        parsed = json.loads(text)
        score = max(-1.0, min(1.0, float(parsed["score"])))
        return score, str(parsed.get("reason", "Claude news analysis"))


def news_by_date(items: Iterable[NewsItem]) -> dict[date, list[NewsItem]]:
    grouped: dict[date, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.published_at, []).append(item)
    return grouped

