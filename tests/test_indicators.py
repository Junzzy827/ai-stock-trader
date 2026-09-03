from ai_stock_trader.indicators import ema, rsi, sma


def test_sma_has_warmup_and_rolling_values():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_ema_has_warmup():
    values = ema([1, 2, 3, 4], 3)
    assert values[:2] == [None, None]
    assert values[2] == 2.0


def test_rsi_is_high_for_rising_series():
    values = rsi(list(range(1, 20)), period=5)
    assert values[-1] == 100.0

