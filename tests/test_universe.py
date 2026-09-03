from datetime import date

import pytest
from conftest import bars

from ai_stock_trader.domain.models import OHLCV
from ai_stock_trader.domain.universe import Universe


def test_a_flat_bar_list_is_grouped_by_symbol():
    universe = Universe.of(bars([100, 101], "A") + bars([200, 201], "B"))
    assert universe.symbols == ("A", "B")
    assert len(universe.bars("A")) == 2


def test_the_timeline_is_the_sorted_union_of_every_symbol():
    a = bars([100, 101], "A", start=date(2025, 1, 1))
    b = bars([200, 201], "B", start=date(2025, 1, 2))
    assert Universe.of(a + b).timeline == (
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
    )


def test_a_missing_bar_resolves_to_none_rather_than_raising():
    universe = Universe.of(bars([100, 101], "A", start=date(2025, 1, 1)))
    assert universe.bar_at("A", date(2025, 1, 1)).close == 100
    assert universe.bar_at("A", date(2025, 1, 9)) is None
    assert universe.position_of("A", date(2025, 1, 2)) == 1


def test_an_existing_universe_passes_through_unchanged():
    universe = Universe.of(bars([100, 101], "A"))
    assert Universe.of(universe) is universe


def test_a_mapping_of_symbols_is_accepted():
    universe = Universe.of({"A": bars([100, 101], "A")})
    assert universe.symbols == ("A",)


def test_unsorted_or_duplicated_bars_are_rejected():
    ordered = bars([100, 101], "A")
    with pytest.raises(ValueError, match="sorted"):
        Universe({"A": tuple(reversed(ordered))})
    with pytest.raises(ValueError, match="duplicate"):
        Universe({"A": (ordered[0], ordered[0])})


def test_bars_filed_under_the_wrong_symbol_are_rejected():
    with pytest.raises(ValueError, match="contains bars"):
        Universe({"A": (OHLCV(date(2025, 1, 1), "B", 1, 1, 1, 1),)})


def test_an_empty_series_is_rejected():
    with pytest.raises(ValueError, match="no bars"):
        Universe({"A": ()})
