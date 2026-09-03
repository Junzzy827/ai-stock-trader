from __future__ import annotations

import argparse
import json

from .adapters.news.rss import fetch_rss_news
from .adapters.prices.csv_source import CsvPriceDataSource
from .app.backtest import run_backtest
from .app.paper import PaperBroker
from .domain.market import JAPAN, MarketSpec
from .domain.risk import RiskConfig
from .domain.strategy import TechnicalNewsStrategy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-assisted stock research and paper trading")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("backtest", "paper"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--csv", required=True, help="normalized OHLCV CSV path")
        sub.add_argument("--symbol", required=True, help="symbol to evaluate")
        sub.add_argument("--capital", type=float, default=100_000)
        sub.add_argument("--commission", type=float, default=0.001)
        sub.add_argument("--rss", action="append", default=[], help="RSS URL; may be repeated")
        sub.add_argument("--lot-size", type=int, default=JAPAN.lot_size, help="shares per lot (TSE default 100)")
        sub.add_argument("--slippage", type=float, default=0.0, help="fraction added to the fill price")
        sub.add_argument("--max-weight", type=float, default=1.0, help="max fraction of equity in one position")
        sub.add_argument("--cash-buffer", type=float, default=0.0, help="fraction of cash kept unspent")
        sub.add_argument("--stop-loss", type=float, help="fixed stop as a fraction below the entry price")
        sub.add_argument("--trailing-stop", type=float, help="trailing stop as a fraction below the peak close")
    subparsers.choices["backtest"].add_argument("--output", help="write JSON result to this path")
    subparsers.choices["paper"].add_argument("--log", default="paper_decisions.jsonl")
    subparsers.choices["paper"].add_argument("--append", action="store_true", help="append to an existing log")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bars = CsvPriceDataSource(args.csv).prices(args.symbol)
    if len(bars) < 2:
        raise SystemExit("at least two bars for the selected symbol are required")
    strategy = TechnicalNewsStrategy()
    market = MarketSpec(lot_size=args.lot_size, commission_rate=args.commission)
    risk_config = RiskConfig(
        max_position_weight=args.max_weight,
        cash_buffer=args.cash_buffer,
        stop_loss_pct=args.stop_loss,
        trailing_stop_pct=args.trailing_stop,
    )
    news = []
    for rss_url in args.rss:
        news.extend(fetch_rss_news(rss_url))

    if args.command == "backtest":
        result = run_backtest(
            bars,
            strategy,
            args.capital,
            args.commission,
            news,
            risk_config=risk_config,
            market=market,
            slippage_rate=args.slippage,
        )
        output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str)
        print(output)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output + "\n")
        return

    result = PaperBroker(args.capital, args.commission, risk_config, market).run(
        bars, strategy, args.log, news, append=args.append
    )
    summary = {
        "log": args.log,
        "decisions": len(result.decisions),
        "trades": len(result.trades),
        "final_equity": result.final_equity,
        "metrics": result.metrics.to_dict(),
        # The last bar has no execution bar yet: this is tomorrow's candidate.
        "pending_signal": result.pending_signal.to_dict() if result.pending_signal else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
