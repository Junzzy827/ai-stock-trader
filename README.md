# AI Stock Trader

テクニカル指標とニュースを根拠に、半自動売買へ進むためのリサーチ基盤です。実弾発注は行いません。

- 日本株の取引慣行（単元100株、率手数料）を前提にした執行モデル
- SMA / RSI / MACDによる説明可能なシグナル
- RSSニュースとキーワード分析、任意のClaude分析アダプター
- 終値で判断し、翌バーの始値で約定するバックテスト
- ポジション上限・損切り・トレーリングストップを持つリスク管理層
- 売買しなかった日も含めて全判断を残すJSONL判断ログ

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
              store(JSONL)
  app/        ユースケース: engine, backtest, paper
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

### 責務の分離

- **Strategy** は「買いたい／売りたい」と根拠だけを返し、数量には関与しません。
- **RiskManager** が単元丸め、資産比率上限、現金バッファ、損切り価格を決めます。戦略を変えても建玉サイズが勝手に変わりません。
- **Broker** が約定価格を決めます。成行は始値、逆指値はバーが引値を貫いた場合に `min(始値, 逆指値)` で約定するため、ギャップダウンを楽観視しません。
- **Portfolio** が状態の唯一の持ち主です。

### 判断ログ

`paper` は1営業日1行のJSONLを書きます。約定だけでなく、見送った日とその理由（`already holding` / `insufficient cash for one lot` / `stopped out` など）も残るため、半自動運用で「なぜ何もしなかったか」を後から追えます。最終バーのシグナルは約定対象のバーがまだ無いので、`pending_signal`（翌営業日の発注候補）として別に出力します。

### 評価指標

最終リターンに加えて、最大ドローダウン、シャープレシオ、勝率、往復回数、平均保有日数、手数料合計を算出します。10万円規模の運用ではリターンより先に最大ドローダウンを見てください。

## 方針と制約

この版は研究・検証用で、証券会社への発注機能は持ちません。ルックアヘッドを避けるため、日付 `t` の終値で計算したシグナルは日付 `t+1` の始値で執行します。

ニュース判定はオフラインで再現できる `KeywordNewsAnalyzer` が既定です。Claudeを使う場合は `ANTHROPIC_API_KEY` を設定し、アプリケーションコードから `ClaudeNewsAnalyzer` を明示的に選択してください。APIキーをリポジトリへ保存しないでください。

現時点のニュース処理には既知の弱点があります。RSSの `pubDate` は解析しますが、銘柄との紐付けが無く、スコアは発行日と完全一致するバーにしか効きません。次のマイルストーンで対応します。

## 次のマイルストーン

1. SQLiteの `DecisionStore` と日次実行ユースケース（`app/daily.py`）、ポジション状態の永続化
2. ニュースの銘柄紐付け、減衰窓、取得時刻と発行時刻の分離、重複排除
3. J-Quantsアダプターとデータ品質チェック（認証・利用規約を確認のうえ追加）
4. 複数銘柄ユニバースと設定ファイル（TOML）化
5. FastAPI + ダッシュボード（判断ログとエクイティカーブの可視化、発注候補の承認フロー）
6. ペーパー期間の評価が終わるまでライブ注文APIは追加しない
