# AI Stock Trader

テクニカル指標とニュースを根拠に、半自動売買へ進むためのリサーチ基盤です。実弾発注は行いません。

- 日本株の取引慣行（単元100株、率手数料）を前提にした執行モデル
- SMA / RSI / MACDによる説明可能なシグナル
- RSSニュースとキーワード分析、任意のClaude分析アダプター
- 終値で判断し、翌バーの始値で約定するバックテスト
- ポジション上限・損切り・トレーリングストップを持つリスク管理層
- 売買しなかった日も含めて全判断を残す判断ログ（JSONL / SQLite）
- SQLiteに状態を持ち、新しい日足だけを処理する日次運用コマンド

## クイックスタート

Python 3.10以上で、リポジトリのルートから実行します。

```bash
python -m pytest
python -m ai_stock_trader.cli backtest \
  --csv data/sample_prices.csv --symbol DEMO --capital 1000000
python -m ai_stock_trader.cli paper \
  --csv data/sample_prices.csv --symbol DEMO --capital 1000000 \
  --log paper_decisions.jsonl
```

単元は100株なので、`--capital` は「株価×100」を十分に上回る必要があります。1株単位の市場を試す場合は `--lot-size 1` を指定します。

RSSを使う場合は `--rss URL` を追加します（複数指定可）。取得に失敗した場合は、運用を止めて原因を確認してください。

## 日次運用

`daily` はSQLiteに現金・ポジション・逆指値・処理済み日付を保存し、**前回以降の新しい足だけ**を処理します。毎朝cronから同じコマンドを叩く運用を想定しています。

```bash
# 初回は手持ちのヒストリを取り込み、以後は差分だけ処理する
python -m ai_stock_trader.cli daily \
  --csv data/prices_7203.csv --symbol 7203 --db trader.db \
  --capital 1000000 --max-weight 0.3 --stop-loss 0.07

# いま何を持っていて、翌営業日の候補は何か
python -m ai_stock_trader.cli status --db trader.db

# 候補に対する人間の判断を記録する
python -m ai_stock_trader.cli approve --db trader.db --date 2025-01-23 --symbol 7203 --note "決算確認済み"
python -m ai_stock_trader.cli reject  --db trader.db --date 2025-01-23 --symbol 7203 --note "地合いが悪い"
```

同じ日を二度流しても状態は進みません（`up_to_date: true`）。書き込みは1回の実行につき1トランザクションで、`commit` されるまで `last_processed_date` は進まないため、途中で落ちた実行は次回そのままやり直されます。口座は `--account` で分けられ、同じDBファイルに複数口座を並べられます。

`paper` は全期間を毎回再計算してJSONLに書き出すコマンドで、戦略を変えた直後の一括検証向けです。継続運用には `daily` を使ってください。

CSVは `date,symbol,open,high,low,close,volume` 形式です。`symbol`列は省略できます。

### リスク管理のオプション

| フラグ | 意味 | 既定 |
| --- | --- | --- |
| `--lot-size` | 1単元の株数 | 100 |
| `--max-weight` | 1銘柄に置ける資産比率の上限 | 1.0 |
| `--cash-buffer` | 常に残す現金の比率 | 0.0 |
| `--stop-loss` | 取得単価からの固定損切り幅 | なし |
| `--trailing-stop` | 高値終値からのトレーリング幅 | なし |
| `--slippage` | 約定価格に上乗せする滑り | 0.0 |
| `--commission` | 約定代金に対する手数料率 | 0.001 |

既定値は「制限なし」に寄せてあり、リスク管理は明示的に有効化する設計です。実運用に近い検証では `--max-weight 0.3 --stop-loss 0.07` のように必ず指定してください。

## 構成

依存の向きを内側（`domain`）に固定した層構成です。

```
ai_stock_trader/
  domain/     依存ゼロの中核: models, indicators, strategy, news_scoring,
              portfolio, risk, market, metrics
  ports.py    Protocolのみ: PriceSource, NewsSource, NewsAnalyzer, Broker,
              DecisionStore
  adapters/   外界とのI/O: prices(CSV), news(RSS/Claude), broker(Simulated),
              store(JSONL / SQLite)
  app/        ユースケース: engine, backtest, paper, daily, status
  cli.py      入口。将来のWeb APIも同じ app/ を呼ぶ
```

### バックテストと運用を同じループで回す

`app/engine.py` の `run_engine` が唯一の評価ループです。

```
各バーごとに:
  1. 保有ポジションの逆指値（STOP）を先に置く
  2. 前日終値で作ったシグナルを RiskManager が数量に変換する
  3. Broker が当日始値／逆指値で約定させる
  4. Portfolio が現金・平均取得単価・実現損益を更新する
  5. Decision を1件記録する（HOLDの日も残す）
```

バックテストと日次運用の違いは「どのバーを渡すか」と「どこへ記録するか」だけです。判断経路が同一なので、検証結果と運用結果が構造的に乖離しません。ライブ発注を足す場合も、`Broker` ポートの別実装を差し込むだけで中核は変わりません。

日次運用では `execute_after` に前回の処理日を渡します。それ以前の足は指標のウォームアップとして戦略には渡されますが、再約定はしません。全期間を一括で流した場合と、1日ずつ差分で流した場合が同じ状態に収束することはテストで固定しています。

### 責務の分離

- **Strategy** は「買いたい／売りたい」と根拠だけを返し、数量には関与しません。
- **RiskManager** が単元丸め、資産比率上限、現金バッファ、損切り価格を決めます。戦略を変えても建玉サイズが勝手に変わりません。
- **Broker** が約定価格を決めます。成行は始値、逆指値はバーが引値を貫いた場合に `min(始値, 逆指値)` で約定するため、ギャップダウンを楽観視しません。
- **Portfolio** が状態の唯一の持ち主です。

### 判断ログと承認フロー

約定だけでなく、見送った日とその理由（`already holding` / `insufficient cash for one lot` / `stopped out` など）も1営業日1件で残ります。半自動運用で知りたいのは「なぜ何もしなかったか」なので、HOLDの日を捨てません。`paper` はJSONL、`daily` はSQLiteに書きます。

最終バーのシグナルは約定対象のバーがまだ無いため、`pending_signal`（翌営業日の発注候補）として分けて出力し、`daily` では `proposals` テーブルに `PROPOSED` で保存します。`approve` / `reject` で人間の判断と理由が記録されるので、「AIの提案と人間の判断のズレ」が後から集計できます。

SQLiteのテーブルは `accounts` / `positions` / `decisions` / `trades` / `equity_history` / `proposals` の6つです。`meta.schema_version` にスキーマ版を持たせてあります。

### 評価指標

最終リターンに加えて、最大ドローダウン、シャープレシオ、勝率、往復回数、平均保有日数、手数料合計を算出します。10万円規模の運用ではリターンより先に最大ドローダウンを見てください。

## 方針と制約

この版は研究・検証用で、証券会社への発注機能は持ちません。ルックアヘッドを避けるため、日付 `t` の終値で計算したシグナルは日付 `t+1` の始値で執行します。

ニュース判定はオフラインで再現できる `KeywordNewsAnalyzer` が既定です。Claudeを使う場合は `ANTHROPIC_API_KEY` を設定し、アプリケーションコードから `ClaudeNewsAnalyzer` を明示的に選択してください。APIキーをリポジトリへ保存しないでください。

現時点のニュース処理には既知の弱点があります。RSSの `pubDate` は解析しますが、銘柄との紐付けが無く、スコアは発行日と完全一致するバーにしか効きません。次のマイルストーンで対応します。

## 次のマイルストーン

1. ニュースの銘柄紐付け、減衰窓、取得時刻と発行時刻の分離、重複排除
2. J-Quantsアダプターとデータ品質チェック（認証・利用規約を確認のうえ追加）
3. 複数銘柄ユニバースと設定ファイル（TOML）化
4. FastAPI + ダッシュボード（判断ログとエクイティカーブの可視化、承認フローのUI化）
5. ペーパー期間の評価が終わるまでライブ注文APIは追加しない

完了済み: 層構成の分離、Portfolio / RiskManager / Broker、統一評価ループ、SQLite永続化と日次実行。
