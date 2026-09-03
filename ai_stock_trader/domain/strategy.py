from __future__ import annotations

from dataclasses import dataclass

from ..ports import NewsAnalyzer
from .indicators import macd, rsi, sma
from .models import BUY, HOLD, NewsItem, OHLCV, SELL, Signal
from .news_scoring import KeywordNewsAnalyzer, dedupe, relevant_weighted_items


@dataclass(frozen=True)
class StrategyConfig:
    short_sma: int = 5
    long_sma: int = 20
    rsi_period: int = 14
    buy_threshold: float = 0.15
    sell_threshold: float = -0.2
    # A headline still counts a few days after publication, just less.
    news_window_days: int = 3
    news_decay_rate: float = 0.5

    def __post_init__(self) -> None:
        if self.news_window_days < 0:
            raise ValueError("news_window_days must not be negative")
        if not 0 < self.news_decay_rate <= 1:
            raise ValueError("news_decay_rate must be in (0, 1]")


class TechnicalNewsStrategy:
    """Long-only, explainable baseline strategy.

    Scores are normalized to -1..1. Signals are calculated at the close; the
    backtester executes them at the next bar's open to avoid look-ahead bias.
    """

    def __init__(self, config: StrategyConfig | None = None, news_analyzer: NewsAnalyzer | None = None):
        self.config = config or StrategyConfig()
        self.news_analyzer = news_analyzer or KeywordNewsAnalyzer()

    def generate(self, bars: list[OHLCV], news: list[NewsItem] | None = None) -> list[Signal]:
        if not bars:
            return []
        closes = [bar.close for bar in bars]
        short = sma(closes, self.config.short_sma)
        long = sma(closes, self.config.long_sma)
        relative_strength = rsi(closes, self.config.rsi_period)
        macd_line, macd_signal = macd(closes)
        news_items = dedupe(news or [])

        signals: list[Signal] = []
        for index, bar in enumerate(bars):
            technical_parts: list[float] = []
            reasons: list[str] = []
            if short[index] is not None and long[index] is not None:
                trend = 1.0 if short[index] > long[index] else -1.0
                technical_parts.append(trend)
                reasons.append("SMA trend=up" if trend > 0 else "SMA trend=down")
            if relative_strength[index] is not None:
                momentum = 0.5 if relative_strength[index] < 30 else (-0.5 if relative_strength[index] > 70 else 0.0)
                technical_parts.append(momentum)
                reasons.append(f"RSI={relative_strength[index]:.1f}")
            if macd_line[index] is not None and macd_signal[index] is not None:
                momentum = 0.5 if macd_line[index] > macd_signal[index] else -0.5
                technical_parts.append(momentum)
                reasons.append("MACD bullish" if momentum > 0 else "MACD bearish")
            technical_score = sum(technical_parts) / len(technical_parts) if technical_parts else 0.0
            window = relevant_weighted_items(
                news_items, bar.symbol, bar.date, self.config.news_window_days, self.config.news_decay_rate
            )
            news_score, news_reason = self.news_analyzer.score(window)
            score = technical_score * 0.7 + news_score * 0.3
            action = BUY if score >= self.config.buy_threshold else SELL if score <= self.config.sell_threshold else HOLD
            signals.append(Signal(bar.date, bar.symbol, action, score, "; ".join(reasons + [news_reason]), technical_score, news_score))
        return signals
