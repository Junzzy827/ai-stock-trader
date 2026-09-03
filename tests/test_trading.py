from datetime import date, timedelta

from ai_stock_trader.backtest import run_backtest
from ai_stock_trader.models import OHLCV
from ai_stock_trader.paper import PaperBroker
from ai_stock_trader.strategy import StrategyConfig, TechnicalNewsStrategy


def bars(prices: list[float]) -> list[OHLCV]:
    start = date(2025, 1, 1)
    return [OHLCV(start + timedelta(days=i), "TEST", price, price, price, price) for i, price in enumerate(prices)]


def test_backtest_executes_on_next_open_and_beats_cash_on_rise():
    result = run_backtest(
        bars(list(range(100, 130))),
        TechnicalNewsStrategy(StrategyConfig(short_sma=2, long_sma=3, rsi_period=2)),
        initial_cash=10_000,
        commission_rate=0,
    )
    assert result.final_equity > result.initial_cash
    assert result.trades
    assert result.trades[0].date == date(2025, 1, 4)


def test_paper_broker_writes_decision_log(tmp_path):
    log_path = tmp_path / "trades.jsonl"
    trades = PaperBroker(10_000, 0).run(bars(list(range(100, 130))), TechnicalNewsStrategy(), log_path)
    assert log_path.exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == len(trades)

