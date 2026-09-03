from __future__ import annotations

def sma(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        result[index] = sum(window) / period
    return result


def ema(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    multiplier = 2 / (period + 1)
    for index in range(period, len(values)):
        current = (values[index] - current) * multiplier + current
        result[index] = current
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value() -> float:
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    result[period] = value()
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
        result[index + 1] = value()
    return result


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None]]:
    if not 0 < fast < slow:
        raise ValueError("expected 0 < fast < slow")
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[float | None] = [
        (fast_ema[index] - slow_ema[index]) if fast_ema[index] is not None and slow_ema[index] is not None else None
        for index in range(len(values))
    ]
    compact = [value for value in line if value is not None]
    signal_compact = ema(compact, signal)
    signal_line: list[float | None] = [None] * len(values)
    compact_index = 0
    for index, value in enumerate(line):
        if value is not None:
            signal_line[index] = signal_compact[compact_index]
            compact_index += 1
    return line, signal_line
