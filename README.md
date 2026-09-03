# AI Stock Trader

テクニカル指標とニュースを根拠に、半自動売買へ進むためのリサーチ基盤です。実弾発注は行いません。

- 日本株の取引慣行（単元100株、率手数料）を前提にした執行モデル
- SMA / RSI / MACDによる説明可能なシグナル
- RSSニュースとキーワード分析、任意のClaude分析アダプター
- 複数銘柄ユニバースを1つの資金で回すバックテストと日次運用
- ポジション上限・損切り・トレーリングストップを持つリスク管理層
- 売買しなかった日も含めて全判断を残す判断ログ（JSONL / SQLite）
- SQLiteに状態を持ち、新しい足だけを処理する日次運用コマンド
- TOML設定ファイルで、口座ごとの実行条件を再現可能にする

## クイックスタート

Python 3.11以上（設定ファイルの読み込みに標準ライブラリの `tomllib` を使います）。外部依存はありません。

```bash
python -m pytest

cp config.example.toml config.toml
python -m ai_stock_trader.cli backtest --config config.toml
python -m ai_stock_trader.cli daily    --config config.toml
python -m ai_stock_trader.cli status   --config config.toml
```

設定ファイルなしでも動きます。

```bash
python -m ai_stock_trader.cli backtest \
  --csv data/sample_universe.csv --symbol 7203 --symbol 9984 \
  --capital 3000000 --max-weight 0.3 --max-positions 3 --stop-loss 0.07
```

CSVは `date,symbol,open,high,low,close,volume` 形式で、1ファイルに複数銘柄を入れられます。`--symbol` を省略するとファイル内の全銘柄が対象になります。`symbol` 列が無いファイルは単一銘柄として扱われ、`--symbol` で名前を与えます。

単元は100株なので、`--capital` は「株価×100×銘柄数」を十分に上回る必要があります。1株単位の市場を試す場合は `--lot-size 1` を指定します。

## 設定ファイル

コマンドラインの引数が増えるほど「そのDBがどの条件で作られたか」が追えなくなります。設定ファイルはその記録でもあります。指定したフラグは常に設定ファイルより優先されます。

```toml
[account]
name = "paper1"
capital = 3000000
database = "trader.db"

[data]
csv = "data/sample_universe.csv"
symbols = ["7203", "6758", "9984"]
rss = ["https://example.com/news.xml"]

[market]
lot_size = 100
commission_rate = 0.001
slippage_rate = 0.0

[strategy]
short_sma = 5
long_sma = 20
buy_threshold = 0.15
sell_threshold = -0.2

[risk]
max_position_weight = 0.3
cash_buffer = 0.05
stop_loss_pct = 0.07
trailing_stop_pct = 0.12
max_positions = 3
```

未知のセクションやキーは黙って無視せずエラーにします。タイプミスが「設定したつもり」で運用に入るのが一番危ないので。

| フラグ | 設定ファイル | 意味 | 既定 |
| --- | --- | --- | --- |
| `--symbol`（複数可） | `data.symbols` | 対象銘柄 | CSV内の全銘柄 |
| `--max-positions` | `risk.max_positions` | 同時保有銘柄数の上限 | 1 |
| `--max-weight` | `risk.max_position_weight` | 1銘柄に置ける資産比率の上限 | 1.0 |
| `--cash-buffer` | `risk.cash_buffer` | 常に残す現金の比率 | 0.0 |
| `--stop-loss` | `risk.stop_loss_pct` | 取得単価からの固定損切り幅 | なし |
| `--trailing-stop` | `risk.trailing_stop_pct` | 高値終値からのトレーリング幅 | なし |
| `--lot-size` | `market.lot_size` | 1単元の株数 | 100 |
| `--commission` | `market.commission_rate` | 約定代金に対する手数料率 | 0.001 |
| `--slippage` | `market.slippage_rate` | 約定価格に上乗せする滑り | 0.0 |

既定値は「制限なし」に寄せてあり、リスク管理は明示的に有効化する設計です。複数銘柄を回すなら `max_positions` と `max_position_weight` は必ず指定してください。

## 日次運用

`daily` はSQLiteに現金・ポジション・逆指値・処理済み日付を保存し、**前回以降の新しい日付だけ**を処理します。毎朝cronから同じコマンドを叩く運用を想定しています。

```bash
python -m ai_stock_trader.cli daily --config config.toml

# いま何を持っていて、翌営業日の候補は何か
python -m ai_stock_trader.cli status --config config.toml

# 候補に対する人間の判断を記録する
python -m ai_stock_trader.cli approve --config config.toml --date 2025-02-28 --symbol 7203 --note "決算確認済み"
python -m ai_stock_trader.cli reject  --config config.toml --date 2025-02-28 --symbol 9984 --note "地合いが悪い"
```

同じ日を二度流しても状態は進みません（`up_to_date: true`）。書き込みは1回の実行につき1トランザクションで、`commit` されるまで `last_processed_date` は進まないため、途中で落ちた実行は次回そのままやり直されます。口座は `--account` で分けられ、同じDBファイルに複数口座を並べられます。

保有中の銘柄をユニバースから外した場合は、評価額を取得単価で据え置き、`stale_symbols` に列挙して知らせます。黙って評価額から消すことはしません。

`paper` は全期間を毎回再計算してJSONLに書き出すコマンドで、戦略を変えた直後の一括検証向けです。継続運用には `daily` を使ってください。

## 構成

依存の向きを内側（`domain`）に固定した層構成です。

```
ai_stock_trader/
  domain/     依存ゼロの中核: models, indicators, strategy, news_scoring,
              portfolio, risk, market, universe, metrics
  ports.py    Protocolのみ: PriceSource, NewsSource, NewsAnalyzer, Broker,
              DecisionStore, StateStore
  adapters/   外界とのI/O: prices(CSV), news(RSS/Claude), broker(Simulated),
              store(JSONL / SQLite)
  app/        ユースケース: engine, backtest, paper, daily, status
  config.py   TOML設定
  cli.py      入口。将来のWeb APIも同じ app/ を呼ぶ
```

### バックテストと運用を同じループで回す

`app/engine.py` の `run_engine` が唯一の評価ループです。

```
銘柄横断の日付ごとに:
  1. 保有ポジションの逆指値（STOP）を先に置く
  2. 手仕舞い → 新規の順に、新規はシグナルの強い順に並べる
  3. 前日終値で作ったシグナルを RiskManager が数量に変換する
  4. Broker が当日始値／逆指値で約定させる
  5. Portfolio が現金・平均取得単価・実現損益を更新する
  6. 銘柄ごとに Decision を1件記録する（HOLDの日も残す）
```

バックテストと日次運用の違いは「どの日付を渡すか」と「どこへ記録するか」だけです。判断経路が同一なので、検証結果と運用結果が構造的に乖離しません。ライブ発注を足す場合も、`Broker` ポートの別実装を差し込むだけで中核は変わりません。

日次運用では `execute_after` に前回の処理日を渡します。それ以前の足は指標のウォームアップとして戦略には渡されますが、再約定はしません。全期間を一括で流した場合と、1日ずつ差分で流した場合が同じ状態に収束することはテストで固定しています。

### 銘柄横断の順序

複数銘柄が同じ資金を取り合うため、1日の中の順序を決め打ちにしています。

- **手仕舞いを新規より先に**実行するので、売却で空いた資金をその日のうちに使えます。
- **新規はシグナルスコアの降順**で処理します。銘柄コード順やCSVの並び順で結果が変わらないようにするためです。
- 資金や `max_positions` で入れなかった銘柄には `insufficient cash for one lot` / `position limit reached` が判断ログに残ります。

銘柄ごとに営業日が違う場合（売買停止、上場時期）は、その日に足がある銘柄だけを評価し、足が無い銘柄は直近終値で評価額に据え置きます。

### 責務の分離

- **Strategy** は「買いたい／売りたい」と根拠だけを返し、数量には関与しません。
- **RiskManager** が単元丸め、資産比率上限、現金バッファ、同時保有数、損切り価格を決めます。戦略を変えても建玉サイズが勝手に変わりません。
- **Broker** が約定価格を決めます。成行は始値、逆指値はバーが引値を貫いた場合に `min(始値, 逆指値)` で約定するため、ギャップダウンを楽観視しません。
- **Portfolio** が状態の唯一の持ち主です。

### 判断ログと承認フロー

約定だけでなく、見送った日とその理由（`already holding` / `insufficient cash for one lot` / `position limit reached` / `stopped out` など）も銘柄×営業日ごとに残ります。半自動運用で知りたいのは「なぜ何もしなかったか」なので、HOLDの日を捨てません。`paper` はJSONL、`daily` はSQLiteに書きます。

最終バーのシグナルは約定対象のバーがまだ無いため、`pending_signals`（翌営業日の発注候補）として分けて出力し、`daily` では `proposals` テーブルに `PROPOSED` で保存します。`approve` / `reject` で人間の判断と理由が記録されるので、「AIの提案と人間の判断のズレ」が後から集計できます。

SQLiteのテーブルは `accounts` / `positions` / `decisions` / `trades` / `equity_history` / `proposals` の6つです。`meta.schema_version` にスキーマ版を持たせてあります。

### 評価指標

最終リターンに加えて、最大ドローダウン、シャープレシオ、勝率、往復回数、平均保有日数、手数料合計を算出します。10万円〜数百万円規模の運用ではリターンより先に最大ドローダウンを見てください。

比較対象のバイ・アンド・ホールドは、ユニバースを等ウェイトで初日に買って持ち切った場合の収益率です。口座全体の `status` には比較対象となる単一銘柄が存在しないため `null` を返します。

## 方針と制約

この版は研究・検証用で、証券会社への発注機能は持ちません。ルックアヘッドを避けるため、日付 `t` の終値で計算したシグナルは日付 `t+1` の始値で執行します。

ニュース判定はオフラインで再現できる `KeywordNewsAnalyzer` が既定です。Claudeを使う場合は `ANTHROPIC_API_KEY` を設定し、アプリケーションコードから `ClaudeNewsAnalyzer` を明示的に選択してください。APIキーをリポジトリへ保存しないでください。

**現時点のニュース処理には既知の弱点があります。** RSSの `pubDate` は解析しますが、銘柄との紐付けが無いため同じスコアが全銘柄に一律で乗り、発行日と完全一致する日付にしか効きません。複数銘柄運用ではこの影響が大きいので、次のマイルストーンで対応します。

## 次のマイルストーン

1. ニュースの銘柄紐付け、減衰窓、取得時刻と発行時刻の分離、重複排除
2. J-Quantsアダプターとデータ品質チェック（認証・利用規約を確認のうえ追加）
3. FastAPI + ダッシュボード（判断ログとエクイティカーブの可視化、承認フローのUI化）
4. ペーパー期間の評価が終わるまでライブ注文APIは追加しない

完了済み: 層構成の分離、Portfolio / RiskManager / Broker、統一評価ループ、SQLite永続化と日次実行、複数銘柄ユニバースとTOML設定。
