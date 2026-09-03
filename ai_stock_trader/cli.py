from __future__ import annotations

import argparse
import json
from datetime import date

from .adapters.news.rss import fetch_rss_news
from .adapters.prices.csv_source import CsvPriceDataSource
from .adapters.store.sqlite import APPROVED, REJECTED, SqliteStore
from .app.backtest import run_backtest
from .app.daily import run_daily
from .app.paper import PaperBroker
from .app.status import account_status
from .config import AppConfig, load_config
from .domain.strategy import TechnicalNewsStrategy


def _add_account_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--config", help="TOML config path")
    sub.add_argument("--db", dest="database", help="SQLite state file")
    sub.add_argument("--account")


def _add_market_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--csv", help="normalized OHLCV CSV path")
    sub.add_argument("--symbol", dest="symbols", action="append", help="symbol; may be repeated")
    sub.add_argument("--rss", action="append", help="RSS URL; may be repeated")
    sub.add_argument("--capital", type=float)
    sub.add_argument("--commission", dest="commission_rate", type=float)
    sub.add_argument("--lot-size", type=int, help="shares per lot (TSE default 100)")
    sub.add_argument("--slippage", dest="slippage_rate", type=float)
    sub.add_argument("--max-weight", dest="max_position_weight", type=float)
    sub.add_argument("--cash-buffer", type=float, dest="cash_buffer")
    sub.add_argument("--stop-loss", dest="stop_loss_pct", type=float)
    sub.add_argument("--trailing-stop", dest="trailing_stop_pct", type=float)
    sub.add_argument("--max-positions", type=int, help="symbols that may be held at once")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-assisted stock research and paper trading")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("backtest", "paper", "daily"):
        sub = subparsers.add_parser(command)
        _add_account_arguments(sub)
        _add_market_arguments(sub)

    subparsers.choices["backtest"].add_argument("--output", help="write JSON result to this path")
    subparsers.choices["paper"].add_argument("--log", default="paper_decisions.jsonl")
    subparsers.choices["paper"].add_argument("--append", action="store_true", help="append to an existing log")

    status = subparsers.add_parser("status")
    _add_account_arguments(status)
    status.add_argument("--recent", type=int, default=10, help="decisions to include")

    for command in ("approve", "reject"):
        decide = subparsers.add_parser(command)
        _add_account_arguments(decide)
        decide.add_argument("--date", required=True, help="proposal date (YYYY-MM-DD)")
        decide.add_argument("--symbol", required=True)
        decide.add_argument("--note", default="")

    return parser


def resolve_config(args: argparse.Namespace) -> AppConfig:
    base = load_config(args.config) if args.config else AppConfig()
    overrides = {
        key: getattr(args, key, None)
        for key in (
            "account",
            "capital",
            "database",
            "csv",
            "symbols",
            "rss",
            "slippage_rate",
            "lot_size",
            "commission_rate",
            "max_position_weight",
            "cash_buffer",
            "stop_loss_pct",
            "trailing_stop_pct",
            "max_positions",
        )
    }
    return base.with_overrides(**overrides)


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    args = build_parser().parse_args()
    config = resolve_config(args)

    if args.command in ("status", "approve", "reject"):
        with SqliteStore(config.database, config.account) as store:
            if args.command == "status":
                _print(account_status(store, args.recent).to_dict())
                return
            status = APPROVED if args.command == "approve" else REJECTED
            matched = store.decide_proposal(date.fromisoformat(args.date), args.symbol, status, args.note)
            store.commit()
            if not matched:
                raise SystemExit(f"no proposal for {args.symbol} on {args.date}")
            _print({"date": args.date, "symbol": args.symbol, "status": status, "note": args.note})
            return

    if not config.csv:
        raise SystemExit("a price CSV is required: pass --csv or set [data].csv in the config")
    try:
        universe = CsvPriceDataSource(config.csv).universe(config.symbols or None)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if len(universe.timeline) < 2:
        raise SystemExit("at least two dates are required to execute a signal")

    strategy = TechnicalNewsStrategy(config.strategy)
    news = [item for url in config.rss for item in fetch_rss_news(url)]

    if args.command == "backtest":
        result = run_backtest(
            universe,
            strategy,
            config.capital,
            config.market.commission_rate,
            news,
            risk_config=config.risk,
            market=config.market,
            slippage_rate=config.slippage_rate,
        )
        output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str)
        print(output)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output + "\n")
        return

    if args.command == "paper":
        result = PaperBroker(
            config.capital, config.market.commission_rate, config.risk, config.market
        ).run(universe, strategy, args.log, news, append=args.append)
        _print(
            {
                "log": args.log,
                "symbols": list(universe.symbols),
                "decisions": len(result.decisions),
                "trades": len(result.trades),
                "final_equity": result.final_equity,
                "metrics": result.metrics.to_dict(),
                "pending_signals": [signal.to_dict() for signal in result.pending_signals],
            }
        )
        return

    with SqliteStore(config.database, config.account) as store:
        result = run_daily(
            store,
            universe,
            strategy,
            initial_cash=config.capital,
            risk_config=config.risk,
            market=config.market,
            slippage_rate=config.slippage_rate,
            news=news,
        )
        _print(result.to_dict())


if __name__ == "__main__":
    main()
