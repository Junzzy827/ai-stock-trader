# AI Stock Trader

テクニカル指標とニュースを根拠に、半自動売買へ進むためのリサーチ基盤です。
現在の初回スコープは、実弾発注を行わずに次を検証できるMVPです。

- OHLCV CSVの読み込み（データ提供元を差し替え可能）
- SMA / RSI / MACDによる説明可能なシグナル
- RSSニュースとキーワード分析、任意のClaude分析アダプター
- 終値で判断し、翌バーの始値で約定するバックテスト
- 初期資金10万円のローカル・ペーパートレードとJSONL判断ログ

## クイックスタート

Python 3.10以上で、リポジトリのルートから実行します。

```bash
python -m pytest
python -m ai_stock_trader.cli backtest \
  --csv data/sample_prices.csv --symbol DEMO --capital 100000
python -m ai_stock_trader.cli paper \
  --csv data/sample_prices.csv --symbol DEMO --log paper_trades.jsonl
```

RSSを使う場合は `--rss URL` を追加します（複数指定可）。取得に失敗した場合は、運用を止めて原因を確認してください。

CSVは `date,symbol,open,high,low,close,volume` 形式です。`symbol`列は省略できます。

## 方針と制約

この初版は研究・検証用で、証券会社への発注機能は持ちません。バックテストはルックアヘッドを避けるため、日付 `t` の終値で計算したシグナルを日付 `t+1` の始値で執行します。売買手数料はCLIの `--commission`（既定0.1%）で指定します。

ニュース判定はオフラインで再現できる `KeywordNewsAnalyzer` が既定です。Claudeを使う場合は `ANTHROPIC_API_KEY` を設定し、アプリケーションコードから `ClaudeNewsAnalyzer` を明示的に選択してください。APIキーをリポジトリへ保存しないでください。

## 計画との対応

1. 要件: 初期資金10万円、テクニカル＋ニュース、半自動をコードと設定に反映。
2. データ基盤: 現在はCSV/RSS。J-Quantsやkabuステーションは認証・利用規約を確認したうえで `PriceDataSource` に追加します。
3. シグナル／バックテスト: 実装済み。戦略の各シグナルに根拠を保存します。
4. ペーパー検証: 実装済み。JSONLログを数週間〜1ヶ月蓄積する運用へ拡張可能です。
5. 半自動運用: 次段階で発注候補・ポジション・ベンチマークを追加します。実弾発注は未実装です。
6. Web/Azure: API、DB、ダッシュボードを次のマイルストーンで追加します。

## 次のマイルストーン

- J-Quants等の実データアダプターとデータ品質チェック
- ニュースの銘柄紐付け、取得時刻、重複排除、ベンチマーク比較
- 約定・保有ポジション・日次評価額をDBへ保存
- バックテスト結果と判断根拠を表示するWebダッシュボード
- ペーパー期間の評価が終わるまでライブ注文APIは追加しない
