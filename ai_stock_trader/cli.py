from __future__ import annotations

import argparse
import json

from .backtest import run_backtest
from .data import CsvPriceDataSource, fetch_rss_news
from .paper import PaperBroker
from .strategy import TechnicalNewsStrategy


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
    subparsers.choices["backtest"].add_argument("--output", help="write JSON result to this path")
    subparsers.choices["paper"].add_argument("--log", default="paper_trades.jsonl")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bars = CsvPriceDataSource(args.csv).prices(args.symbol)
    if len(bars) < 2:
        raise SystemExit("at least two bars for the selected symbol are required")
    strategy = TechnicalNewsStrategy()
    news = []
    for rss_url in args.rss:
        news.extend(fetch_rss_news(rss_url))
    if args.command == "backtest":
        result = run_backtest(bars, strategy, args.capital, args.commission, news)
        output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str)
        print(output)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as file:
                file.write(output + "\n")
    else:
        trades = PaperBroker(args.capital, args.commission).run(bars, strategy, args.log, news)
        print(json.dumps({"trades": len(trades), "log": args.log}, ensure_ascii=False))


if __name__ == "__main__":
    main()
