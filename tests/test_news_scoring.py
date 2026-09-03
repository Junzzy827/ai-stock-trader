from datetime import date

import pytest

from ai_stock_trader.domain.models import NewsItem
from ai_stock_trader.domain.news_scoring import (
    KeywordNewsAnalyzer,
    decay_weight,
    dedupe,
    relevant_weighted_items,
)

DAY = date(2025, 1, 10)


def item(published: date, title: str, url: str = "", symbols: tuple[str, ...] = ()) -> NewsItem:
    return NewsItem(published, title, "", url, symbols)


def test_dedupe_keeps_the_first_item_per_url():
    first = item(DAY, "同じ記事", url="http://x/1")
    second = item(DAY, "同じ記事（転載）", url="http://x/1")
    assert dedupe([first, second]) == [first]


def test_dedupe_falls_back_to_title_and_date_without_a_url():
    a = item(DAY, "決算発表")
    b = item(DAY, "決算発表")
    c = item(date(2025, 1, 11), "決算発表")
    assert dedupe([a, b, c]) == [a, c]


def test_decay_weight_is_one_on_the_publication_day():
    assert decay_weight(DAY, DAY, 0.5) == 1.0


def test_decay_weight_halves_each_day_at_rate_one_half():
    assert decay_weight(DAY, date(2025, 1, 12), 0.5) == pytest.approx(0.25)


def test_decay_weight_is_zero_for_news_published_after_as_of():
    assert decay_weight(date(2025, 1, 12), DAY, 0.5) == 0.0


def test_relevant_items_exclude_anything_outside_the_window():
    items = [item(date(2025, 1, 6), "old"), item(DAY, "today")]
    result = relevant_weighted_items(items, "TEST", DAY, window_days=3, decay_rate=0.5)
    assert [entry.title for entry, _ in result] == ["today"]


def test_relevant_items_never_look_ahead_of_as_of():
    items = [item(date(2025, 1, 11), "tomorrow's news")]
    assert relevant_weighted_items(items, "TEST", DAY, window_days=5, decay_rate=0.5) == []


def test_market_wide_news_applies_to_every_symbol():
    market_wide = item(DAY, "日経平均が上昇")
    assert relevant_weighted_items([market_wide], "7203", DAY, 3, 0.5)
    assert relevant_weighted_items([market_wide], "6758", DAY, 3, 0.5)


def test_symbol_tagged_news_does_not_leak_to_other_symbols():
    tagged = item(DAY, "トヨタ決算", symbols=("7203",))
    assert relevant_weighted_items([tagged], "7203", DAY, 3, 0.5)
    assert relevant_weighted_items([tagged], "6758", DAY, 3, 0.5) == []


def test_keyword_analyzer_score_is_zero_for_no_news():
    assert KeywordNewsAnalyzer().score([]) == (0.0, "news keywords: +0.0/-0.0")


def test_keyword_analyzer_weighs_older_headlines_less():
    analyzer = KeywordNewsAnalyzer()
    full_weight, _ = analyzer.score([(item(DAY, "増益で上方修正"), 1.0)])
    half_weight, _ = analyzer.score([(item(DAY, "増益で上方修正"), 0.5)])
    assert half_weight < full_weight
    assert half_weight > 0


def test_keyword_analyzer_score_is_clamped_to_the_unit_interval():
    analyzer = KeywordNewsAnalyzer()
    very_positive = [(item(DAY, "増益 上方修正 成長 受注"), 1.0)] * 5
    score, _ = analyzer.score(very_positive)
    assert score == 1.0
