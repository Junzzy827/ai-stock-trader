from datetime import date
from unittest.mock import patch

from ai_stock_trader.adapters.news.rss import fetch_rss_news

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>7203が上方修正</title>
  <description>増益見通し</description>
  <link>http://example.com/1</link>
  <pubDate>Mon, 06 Jan 2025 09:00:00 +0900</pubDate>
</item>
<item>
  <title>重複記事</title>
  <link>http://example.com/1</link>
  <pubDate>Mon, 06 Jan 2025 10:00:00 +0900</pubDate>
</item>
<item>
  <title>日付なし記事</title>
  <link>http://example.com/2</link>
</item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def fetch(feed: str = FEED):
    with patch("ai_stock_trader.adapters.news.rss.urlopen", return_value=FakeResponse(feed.encode())):
        return fetch_rss_news("http://example.com/feed.xml")


def test_pub_date_is_parsed_into_the_published_date():
    items = fetch()
    assert items[0].published_at == date(2025, 1, 6)


def test_items_sharing_a_link_are_deduplicated_within_one_fetch():
    items = fetch()
    assert len(items) == 2  # the duplicate of item 1, plus the dateless item


def test_fetched_at_is_stamped_on_every_item():
    items = fetch()
    assert all(item.fetched_at == date.today() for item in items)


def test_an_item_without_pub_date_falls_back_to_the_fetch_date():
    items = fetch()
    dateless = next(item for item in items if item.url == "http://example.com/2")
    assert dateless.published_at == date.today()


def test_a_fresh_fetch_carries_no_symbol_tags_yet():
    assert all(item.symbols == () for item in fetch())
