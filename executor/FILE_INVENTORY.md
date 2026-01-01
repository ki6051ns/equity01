# execution / executor ファイル一覧

## execution/ ディレクトリ（既存・旧設計）

### コア機能

| ファイル | 説明 |
|---------|------|
| `build_order_intent.py` | Δweightからnotionalを計算してorder_intent（DataFrame）を構築。リバランス数量計算。 |
| `build_hedge_intent.py` | βヘッジ用のorder_intentを生成（CFD/現物インバースETF）。 |
| `read_latest.py` | core成果物（daily_portfolio_guarded.parquet）の最新日を読み込む。 |
| `run_dryrun.py` | execution dry-runの実行入口。order_intent生成・order_events記録。 |
| `state_store.py` | 前日スナップショット管理・latest_date進行ガード（run_guard）。 |

### 補助機能

| ファイル | 説明 |
|---------|------|
| `order_id.py` | latest_date + symbol + sideからdeterministicなorder_keyを生成（冪等性確保）。 |
| `order_store.py` | 注文イベントログを追記保存（jsonl形式）。INTENT/SUBMITTED等の状態管理。 |
| `write_order_intent.py` | order_intentをCSV/Parquetに出力。 |
| `exceptions.py` | リトライ可能/不可能な例外を分類（RetryableError/FatalError等）。 |
| `retry.py` | リトライデコレータ（簡易版）。 |
| `config.json` | 実行設定（aum, leverage_ratio, margin_buffer等）。 |

### metrics/ サブディレクトリ

| ファイル | 説明 |
|---------|------|
| `collect_metrics.py` | execution_outputs/のorder_intent_*.csvを走査して日次メトリクスを集計。 |

### 出力ディレクトリ

| ディレクトリ | 説明 |
|------------|------|
| `execution_outputs/` | order_intent_*.csv/parquetの出力先。 |
| `execution_state/` | state.json, latest_weights.parquetの保存先。 |

---

## executor/ ディレクトリ（新設計・Intent-based）

### コア機能

| ファイル | 説明 |
|---------|------|
| `models.py` | Intentスキーマ定義（OrderIntent/HedgeIntent/ExecutionRun）。dataclassベース。 |
| `build_intent.py` | core成果物からOrderIntent/HedgeIntentを生成。数量（qty）はexecutor側で確定。 |
| `precheck.py` | 事前チェック（休日・余力・価格鮮度・通信）。Fail-safe原則。 |
| `dryrun.py` | Dry-run実行（PRE_SUBMITモード）。注文画面まで進み、最終クリックだけ実行しない。 |
| `config.json` | 実行設定（mode: DRYRUN_PRE_SUBMIT/LIVE_SUBMIT, stop_before_submit等）。 |

### adapters/ サブディレクトリ（証券会社アダプター）

| ファイル | 説明 |
|---------|------|
| `sbi_cash.py` | SBI証券 現物取引アダプター。UI操作・発注処理（骨格のみ、Selenium未実装）。 |
| `sbi_cfd.py` | SBI証券 CFD取引アダプター。UI操作・発注処理（骨格のみ、Selenium未実装）。 |

### 出力ディレクトリ

| ディレクトリ | 説明 |
|------------|------|
| `archives/runs/` | 実行ログ（run_{run_id}.json）の保存先。1 run = 1ファイル。 |

---

## 設計の違い

### execution/（既存）
- DataFrameベースのorder_intent
- CSV/Parquet形式での出力
- order_events.jsonl形式のイベントログ
- 実行入口: `run_dryrun.py`

### executor/（新設計）
- dataclassベースのIntent（OrderIntent/HedgeIntent）
- JSON形式の実行ログ（ExecutionRun）
- PRE_SUBMITモード対応（UI反映まで）
- 実行入口: `dryrun.py`

---

## 移行方針

executor/が正本として設計されているため、execution/からexecutor/への移行を推奨：

1. **現状**: execution/でorder_intent生成まで実装済み
2. **移行**: executor/でIntent-based設計に移行
3. **最終**: executor/を正本として、execution/は非推奨（deprecated）

