from __future__ import annotations

import json
import os
from typing import Iterable
from urllib.request import Request, urlopen

from ...domain.models import NewsItem


class ClaudeNewsAnalyzer:
    """Optional Claude API adapter; never called unless explicitly selected."""

    def __init__(self, api_key: str | None = None, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeNewsAnalyzer")

    def score(self, items: Iterable[NewsItem]) -> tuple[float, str]:
        payload_items = [{"title": item.title, "summary": item.summary, "url": item.url} for item in items]
        if not payload_items:
            return 0.0, "no news"
        prompt = (
            "Evaluate the market impact of these headlines for a single stock. "
            "Return JSON only with score (-1 to 1) and reason (short Japanese text).\n"
            + json.dumps(payload_items, ensure_ascii=False)
        )
        body = json.dumps(
            {"model": self.model, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}
        ).encode()
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
