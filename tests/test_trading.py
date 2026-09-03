from datetime import date

from conftest import bars

from ai_stock_trader.app.backtest import run_backtest
from ai_stock_trader.app.paper import PaperBroker
from ai_stock_trader.domain.market import MarketSpec
from ai_stock_trader.domain.risk import RiskConfig
from ai_stock_trader.domain.strategy import StrategyConfig, TechnicalNewsStrategy

FAST = StrategyConfig(short_sma=2, long_sma=3, rsi_period=2)


def test_backtest_executes_on_next_open_and_beats_cash_on_rise():
    result = run_backtest(
        bars(list(range(100, 130))),
        TechnicalNewsStrategy(FAST),
        initial_cash=1_000_000,
        commission_rate=0,
    )
    assert result.final_equity > result.initial_cash
    assert result.trades
    # The signal is formed at the 2025-01-03 close and filled at the next open.
    assert result.trades[0].date == date(2025, 1, 4)


def test_backtest_buys_whole_lots_only():
    result = run_backtest(bars(list(range(100, 130))), TechnicalNewsStrategy(FAST), initial_cash=1_000_000)
    assert result.trades[0].quantity % 100 == 0


def test_backtest_skips_entry_when_one_lot_is_unaffordable():
    result = run_backtest(bars(list(range(100, 130))), TechnicalNewsStrategy(FAST), initial_cash=1_000)
    assert result.trades == ()
    assert any(decision.note == "insufficient cash for one lot" for decision in result.decisions)


def test_max_position_weight_limits_exposure():
    capped = run_backtest(
        bars(list(range(100, 130))),
        TechnicalNewsStrategy(FAST),
        initial_cash=1_000_000,
        commission_rate=0,
        risk_config=RiskConfig(max_position_weight=0.5),
    )
    full = run_backtest(
        bars(list(range(100, 130))),
        TechnicalNewsStrategy(FAST),
        initial_cash=1_000_000,
        commission_rate=0,
    )
    assert capped.trades[0].quantity * 2 <= full.trades[0].quantity + 100


def test_equity_curve_covers_every_bar():
    prices = list(range(100, 130))
    result = run_backtest(bars(prices), TechnicalNewsStrategy(FAST), initial_cash=1_000_000)
    assert len(result.equity_curve) == len(prices)
    assert len(result.decisions) == len(prices) - 1


def test_paper_broker_logs_every_decision_not_just_trades(tmp_path):
    log_path = tmp_path / "decisions.jsonl"
    result = PaperBroker(1_000_000, 0).run(bars(list(range(100, 130))), TechnicalNewsStrategy(FAST), log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(result.decisions)
    assert len(result.trades) < len(lines)


def test_us_market_spec_allows_single_share_lots():
    result = run_backtest(
        bars(list(range(100, 130))),
        TechnicalNewsStrategy(FAST),
        initial_cash=10_000,
        commission_rate=0,
        market=MarketSpec(name="US", currency="USD", lot_size=1),
    )
    assert result.trades
    assert result.trades[0].quantity % 100 != 0
