from datetime import date

from ai_stock_trader.adapters.news.matching import tag_all, tag_symbols
from ai_stock_trader.domain.models import NewsItem

DAY = date(2025, 1, 10)
ALIASES = {"7203": ("トヨタ自動車", "トヨタ"), "6758": ("ソニーグループ", "ソニー")}


def item(title: str, summary: str = "") -> NewsItem:
    return NewsItem(DAY, title, summary)


def test_a_matching_alias_tags_the_item():
    tagged = tag_symbols(item("トヨタ自動車が増益"), ALIASES)
    assert tagged.symbols == ("7203",)


def test_the_ticker_code_itself_is_also_matched():
    tagged = tag_symbols(item("7203が急伸"), ALIASES)
    assert tagged.symbols == ("7203",)


def test_a_match_in_the_summary_counts_too():
    tagged = tag_symbols(item("決算まとめ", "ソニーグループが上方修正"), ALIASES)
    assert tagged.symbols == ("6758",)


def test_multiple_matches_tag_every_symbol_involved():
    tagged = tag_symbols(item("トヨタとソニーが提携"), ALIASES)
    assert set(tagged.symbols) == {"7203", "6758"}


def test_no_match_leaves_the_item_market_wide():
    tagged = tag_symbols(item("日経平均が反発"), ALIASES)
    assert tagged.symbols == ()


def test_tagging_preserves_the_other_fields():
    original = NewsItem(DAY, "トヨタ決算", "summary", "http://x/1", fetched_at=DAY)
    tagged = tag_symbols(original, ALIASES)
    assert (tagged.title, tagged.summary, tagged.url, tagged.fetched_at) == (
        original.title,
        original.summary,
        original.url,
        original.fetched_at,
    )


def test_tag_all_is_a_no_op_without_aliases():
    items = [item("トヨタ決算")]
    assert tag_all(items, {}) is items


def test_tag_all_tags_every_item():
    items = [item("トヨタ決算"), item("ソニー決算")]
    tagged = tag_all(items, ALIASES)
    assert [t.symbols for t in tagged] == [("7203",), ("6758",)]
