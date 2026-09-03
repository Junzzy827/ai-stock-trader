"""A set of symbols sharing one calendar.

Symbols do not always have a bar on every date (halts, listings, different
exchanges), so the engine walks the union of dates and asks the universe which
symbols are tradable on each one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Iterable, Mapping

from .models import OHLCV


@dataclass(frozen=True)
class Universe:
    series: Mapping[str, tuple[OHLCV, ...]]
    _index: dict[str, dict[Date, int]] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        normalized: dict[str, tuple[OHLCV, ...]] = {}
        index: dict[str, dict[Date, int]] = {}
        for symbol, bars in self.series.items():
            ordered = tuple(bars)
            if not ordered:
                raise ValueError(f"{symbol} has no bars")
            days = [bar.date for bar in ordered]
            if days != sorted(days):
                raise ValueError(f"{symbol} bars must be sorted by date")
            if len(set(days)) != len(days):
                raise ValueError(f"{symbol} has duplicate dates")
            mismatched = {bar.symbol for bar in ordered} - {symbol}
            if mismatched:
                raise ValueError(f"{symbol} contains bars for {sorted(mismatched)}")
            normalized[symbol] = ordered
            index[symbol] = {day: position for position, day in enumerate(days)}
        object.__setattr__(self, "series", normalized)
        object.__setattr__(self, "_index", index)

    @classmethod
    def of(cls, data: "Universe | Mapping[str, Iterable[OHLCV]] | Iterable[OHLCV]") -> "Universe":
        """Accept a universe, a symbol mapping, or a single symbol's bars."""
        if isinstance(data, Universe):
            return data
        if isinstance(data, Mapping):
            return cls({symbol: tuple(bars) for symbol, bars in data.items()})
        grouped: dict[str, list[OHLCV]] = {}
        for bar in data:
            grouped.setdefault(bar.symbol, []).append(bar)
        return cls({symbol: tuple(bars) for symbol, bars in grouped.items()})

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.series))

    @property
    def timeline(self) -> tuple[Date, ...]:
        days: set[Date] = set()
        for bars in self.series.values():
            days.update(bar.date for bar in bars)
        return tuple(sorted(days))

    def bars(self, symbol: str) -> tuple[OHLCV, ...]:
        return self.series[symbol]

    def position_of(self, symbol: str, day: Date) -> int | None:
        return self._index.get(symbol, {}).get(day)

    def bar_at(self, symbol: str, day: Date) -> OHLCV | None:
        position = self.position_of(symbol, day)
        return self.series[symbol][position] if position is not None else None

    def is_empty(self) -> bool:
        return not self.series
