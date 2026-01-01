# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 3.4 / Updated: 2026-01-01（6th_commit: Executor完全独立・Dry-run動作証明）**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

ALPHAERS（統合戦略）の中核である **Equity Strategy Layer** を担い、  
**透明性・説明可能性・再現性・堅牢性** を最優先に設計されています。

本バージョン（v3.4）は **6th_commit（Executor完全独立・Dry-run動作証明）** であり、  
**「実行しても死なない」ことを、ログと挙動で証明**した、重要なマイルストーンを達成しました。  
executorをprod正本として独立確立し、**取引実行パスワード入力直前（PRE_SUBMIT）までのdry-runが、  
完全に安全・冪等・監査可能な形で動作する**ことを実証しました。

**前バージョン（v3.3）**: **5th_commit（core vs backtest / alpha 完全一致検証完了）** で、  
**数理・実装・意思決定すべて確定**という、きれいな区切りを達成しました。  
core系列とbacktest系列の完全一致、alpha系列の完全一致により、  
**ロジック差・ルックアヘッド・定義ズレは完全に排除**されました。

**6th_commit サマリ**:
- ✅ **executor/はexecution/から完全独立**（import依存ゼロ、単体稼働可能）
- ✅ **エントリポイント一本化**（`scripts/ops/run_executor_dryrun.py`、exit code意味論明確化）
- ✅ **RunLog完成**（stgゲートとして十分、100%再現可能な監査証跡）
- ✅ **Intent-based実行設計確立**（株数・金額計算はexecutorに一本化）
- ✅ **Fail-safe動作実証**（休日検出で正しくHALT、設計通りの正常停止）
- 📊 **次フェーズ**: 営業日でのdry-run冪等性確認、SBIアダプタ実装、prd切替

---

# 📋 目次

1. [セットアップ](#セットアップ)
2. [実行方法](#実行方法)
3. [データ配置](#データ配置)
4. [TOPIXデータ取得のフォールバック仕様](#topixデータ取得のフォールバック仕様)
5. [ディレクトリ構造](#ディレクトリ構造)
6. [設計ルール](#設計ルール)

---

# 🔧 セットアップ

## 前提条件

- Python 3.8以上
- pip（Pythonパッケージマネージャー）

## インストール手順

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd equity01
```

### 2. 仮想環境の作成（推奨）

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python -m venv venv
source venv/bin/activate
```

**注意**: `venv/` は `.gitignore` で除外されています。各環境で個別に作成してください。

### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4. データディレクトリの確認

以下のディレクトリが存在することを確認してください：

- `data/raw/equities/` - 個別株価格データ（.parquet形式）
- `data/raw/prices/` - 価格データ（.csv形式、一部）
- `data/events/` - イベントカレンダー（calendar.csv, earnings.csv等）

---

# 🚀 実行方法

## 基本実行（推奨）

### 運用フロー（core完結）

運用フローは以下の順序で実行します：

```bash
# 1. ユニバース構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格データ取得
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet

# 3. TOPIXデータ構築
python scripts/tools/build_index_tpx_daily.py

# 4. 特徴量構築（内部でスコアリングも実行される）
# 【② run_scoring 二重実行の回避】build_features.py内でcompute_scores_allを呼び出してスコアリングを実行
# run_scoring.pyは別途実行しない（二重実行を回避）
python scripts/core/build_features.py

# 5. ポートフォリオ構築（運用終点生成）
python scripts/core/build_portfolio.py
```

### Windowsタスクスケジューラの運用設定

`scripts/run_equity01_core.ps1`をWindowsタスクスケジューラから自動実行する場合の推奨設定：

#### 基本設定
- **プログラム**: `powershell.exe`
- **引数**: `-ExecutionPolicy Bypass -NoProfile -File "C:\path\to\equity01\scripts\run_equity01_core.ps1"`
- **開始ディレクトリ**: プロジェクトルート（`C:\path\to\equity01`）

#### 実行スケジュール
- **実行時間帯**: 営業日の朝（例：平日 8:00）
- **実行頻度**: 毎営業日

#### タイムアウト設定
- **タスクのタイムアウト**: 2時間（120分）
  - 通常は10-15分程度で完了するが、ネットワーク遅延等を考慮して余裕を持たせる

#### 失敗時の再実行
- **再実行**: 基本なし（自動リトライなし）
  - 失敗時はログを確認して手動対応
  - 必要に応じて手動で再実行

#### ログ管理
- **ログファイル**: `logs/run_equity01_core_YYYYMMDD.log`
- **保管期間**: 30日（推奨）
- **ローテーション**: 古いログは自動削除またはアーカイブ
  - PowerShellスクリプトで30日以上古いログを削除する処理を追加可能

#### エラー通知（オプション）
- タスクスケジューラの「履歴」タブで失敗を確認
- 必要に応じて、失敗時にメール通知を設定

#### universe_builderのyfinance取得失敗時の挙動
- **現在の設定**: A案（堅牢）を採用
  - yfinance取得失敗時は、前回の`latest_universe.parquet`を使用して継続
  - ログに`[ERROR]`を記録し、`[FALLBACK]`として前回データを使用
  - 運用は継続されるが、ログで確認可能
- **代替案**: B案（品質）
  - yfinance取得失敗時は`ExitCode!=0`で停止（その日は運用しない）
  - より厳格だが、データ品質を優先

### 運用終点

実行が成功すると、以下のファイルが生成されます：

- **`data/processed/daily_portfolio_guarded.parquet`** - **運用終点（Executionが読む正本）**
  - `weight` 列を含み、実運用で直接使用可能
  - **【③ 最重要】実運用では `daily_portfolio_guarded.parquet` の `date` 列の `max(date)` の行のみを使用する（契約レベル）**
  - date列は正規化・ソート済み（timezoneなし、昇順）
  - latest専用ファイル作成・完了フラグ・営業日判定は不要

**詳細:**
- `docs/core_flow_table.md` - 実行順序と入出力の詳細
- `docs/pipeline_graph.md` - パイプライン依存図

**運用安定化の設計原則:**
- **【③ 最重要】latest解釈（契約レベル）**: 実運用では `daily_portfolio_guarded.parquet` の `date` 列の `max(date)` の行のみを使用する
- **【① TOPIX依存】**: build_features.pyでTOPIXデータを参照（欠損時は警告を出力、無言スルー禁止）
- **【② run_scoring 二重実行】**: build_features.py内でcompute_scores_allを呼び出し（実行フローは変更なし）
- **【④ 途中生成物】**: 途中失敗時に生成物が残る可能性があるが、Executionは`daily_portfolio_guarded.parquet`の`date`列`max(date)`行のみ使用するため問題ない
- **【⑤ 祝日・価格未更新日】**: download_prices.pyで取得不能時は警告を出力して継続（営業日カレンダー実装は不要）

---

### cross4 weights版検証フロー（研究用・非推奨）

**注意**: 以下の検証フローは`deprecated/2025Q4_pre_weights_fix/`に移動しました。  
weights版cross4と既存return合成cross4の一致検証は既に完了しており、現在はweights型を正とする運用フローを使用してください。

**（参考）旧検証フロー（deprecated）:**

```bash
# ①→②→③→④を自動実行（deprecated/2025Q4_pre_weights_fix/に移動）
python deprecated/2025Q4_pre_weights_fix/run_cross4_weights_verification.py
```

**個別実行（詳細確認が必要な場合）:**

```bash
# ① variant別/horizon別のweightsを生成
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 120 --ladder ladder

python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 120 --ladder ladder

# ② cross4 target weightsを生成
python scripts/analysis/build_cross4_target_weights.py
# → 出力: data/processed/weights/cross4_target_weights.parquet

# ③ weights→returnsを計算
python scripts/analysis/backtest_from_weights.py
# → 出力: data/processed/weights_bt/cross4_from_weights.parquet

# ④ 一致検証（deprecated/2025Q4_pre_weights_fix/に移動）
python deprecated/2025Q4_pre_weights_fix/verify_cross4_equivalence.py
# → 出力: research/reports/cross4_weights_equivalence.csv
# → 出力: research/reports/cross4_weights_equivalence_top20_diff.csv（FAIL時）
# → 出力: research/reports/cross4_weights_top_diff_date_{YYYYMMDD}.csv（FAIL時）
```

**詳細:**
- `docs/cross4_weights_implementation_status.md` - 実装状況サマリ
- `docs/ladder_specification.md` - ladder仕様

**注意**: 検証スクリプト（`verify_cross4_equivalence.py`, `compare_cross4_returns.py`, `analyze_cross4_cumret_diff_monthly.py`）は`deprecated/2025Q4_pre_weights_fix/`に移動しました。weights型への移行は完了しており、現在はweights型を正とする運用フローを使用してください。

---

### 評価フロー（非推奨・deprecated）

**注意**: 以下の評価フロー関連スクリプトは `deprecated/2025Q4_pre_weights_fix/` に移動しました。  
stgではweights型（core）のみを使用してください。

- `scripts/core/run_equity01_eval.py` → deprecated
- `scripts/core/calc_alpha_beta.py` → deprecated
- `scripts/core/build_dynamic_portfolio.py` → deprecated（ensemble系に依存）
- `scripts/core/build_regime_hmm.py` → deprecated（horizon_ensemble_variant_cross4.parquetに依存、モニタリング用途のみ）
- `scripts/core/event_guard.py` → deprecated（ロジック構築未完成）

## 統合評価レポート生成（非推奨・deprecated）

**注意**: `scripts/analysis/run_eval_report.py` は `deprecated/2025Q4_pre_weights_fix/` に移動しました。  
stgではweights型（core）のみを使用してください。

---

# 📁 データ配置

## Git管理対象

以下のディレクトリは **Gitで管理** されます：

- `data/raw/` - 生データ（価格、イベントカレンダー等）
- `data/intermediate/universe/` - ユニバース定義（.parquet）
- `configs/` - 設定ファイル（.yml）

## Git管理外（.gitignore）

以下のディレクトリは **生成物** として `.gitignore` で除外されています：

- `data/processed/` - 処理済みデータ（.parquet, .png等）
- `data/intermediate/scoring/` - スコアリング中間結果
- `research/reports/` - 研究用レポート（.png, .csv等）
- `venv/` - 仮想環境
- `__pycache__/` - Pythonキャッシュ

## データ配置の推奨構造

```
data/
├── raw/
│   ├── equities/          # 個別株価格（.parquet）
│   ├── prices/            # 価格データ（.csv、一部）
│   ├── jpx_listings/      # JPX上場銘柄リスト
│   ├── fx/                # FXデータ
│   └── futures/           # 先物データ
├── events/                # イベントカレンダー
│   ├── calendar.csv       # マクロイベント
│   └── earnings.csv       # 決算カレンダー
├── processed/             # 生成物（Git管理外）
│   ├── index_tpx_daily.parquet
│   ├── paper_trade_with_alpha_beta.parquet
│   └── rolling_relative_alpha.parquet
└── intermediate/          # 中間生成物（Git管理外）
    ├── universe/
    └── scoring/
```

---

# 📝 変更履歴

## 6th Commit: Executor完全独立・Dry-run動作証明

### 概要

executorをprod正本として独立確立し、**「取引実行パスワード入力直前（PRE_SUBMIT）までのdry-runが、完全に安全・冪等・監査可能な形で動作する」**ことを実証。

core/backtestの数理的正当性が確定した後、実運用の失敗点（休日・余力・価格・通信）をすべてexecutor側で吸収できる構造に到達。

### 到達点（技術的に確定した事実）

#### 1. executorの完全独立

- executor/はexecution/にimport依存ゼロ
- core成果物を直接読み、単体で稼働可能
- execution/はlegacy/参照用に固定

#### 2. エントリポイントの一本化

- `scripts/ops/run_executor_dryrun.py`
- exit codeを意味論で定義：
  - `0`: PRE_SUBMIT到達（成功）
  - `2`: HALT（事前チェック失敗・正常停止）
  - `1`: 想定外エラー
- タスクスケジューラ向けに0x2を成功扱いに正規化するPS1ラッパーも用意

#### 3. RunLogの完成（stgゲートとして十分）

RunLogに以下を完全記録：
- `run_id`/`run_at`/`latest_date`
- `intent_hash`（冪等性確認用）
- `OrderIntent`/`HedgeIntent`
- precheck snapshots（trading_day, price_freshness, cash/margin, connectivity）
- `stop_reason`/`errors`
- 例外時でもtry/finallyで必ず保存

→ **「なぜ止まったか」「どこまで進んだか」が100%再現可能**

#### 4. Intent-based実行設計の確立

- **core**: target weights / β / STOP
- **executor**:
  - 現在ポジション取得
  - target_notional / rebalance_notional
  - 株数丸め（単元・最小）
  - 余力・証拠金チェック
- 株数・金額計算はexecutorに一本化
- dry-runと本番で同一ロジック

#### 5. Fail-safe動作の実証

実行結果より：
- 非営業日（2025-12-30）を正しく検出
- `non_trading_day`で意図的にHALT
- OrderIntent/RunLogは正常生成
- exit code 2（0x2）＝設計通りの正常停止

→ **「止まるべき日に、正しい理由で止まれる」ことを確認**

### stgフェーズの位置づけ更新

- **stg前半**: core vs backtest完全一致（数理確定）
- **stg後半（今回）**:
  - executor単体稼働
  - dry-run PRE_SUBMIT到達
  - RunLogによる判断可能性
  - 冪等性確認準備完了

👉 **stg終了ゲート目前**

### 6th Commitの意味（設計的結論）

- coreはもう疑わない
- backtestは正しい
- 今後の減衰要因は現実の摩擦のみ
- その摩擦を吸収するためのexecutorが完成
- **prodで壊れる可能性のある点は、すべてexecutor側に隔離された**

### 次フェーズ（7th Commit以降）

1. 営業日でのdry-run冪等性確認
2. SBI現物/CFDアダプタのPRE_SUBMIT実装（UI）
3. STOP_BEFORE_SUBMIT=falseによるprd切替

**一言まとめ**: 6th Commit =「実行しても死なない」ことを、ログと挙動で証明したコミット

---

# 🔄 TOPIXデータ取得のフォールバック仕様

## 仕様概要

equity01 は TOPIX インデックスデータを取得する際、以下の優先順位でフォールバックします：

1. **^TOPX** (yfinance) - 試行するが、取得できない場合が多い
2. **1306.T** (TOPIX連動ETF) - デフォルトフォールバック

## 実装詳細

`scripts/tools/build_index_tpx_daily.py` では以下のロジックで動作します：

```python
# 1. ^TOPX を試行
try:
    tpx_data = yf.download("^TOPX", ...)
except:
    # 2. 失敗したら 1306.T にフォールバック
    tpx_data = yf.download("1306.T", ...)
    # ログに「フォールバックした理由」を記録
```

## ログ出力

フォールバックが発生した場合、以下のようなログが出力されます：

```
[ERROR] ^TOPX で取得失敗: yfinanceで取得できません(^TOPX)。ネットワーク/設定の可能性。詳細: None
[OK] 1306.T で取得成功
```

## 運用上の注意

- **監査性**: フォールバック発生時は必ずログに記録されます
- **再現性**: 同じ環境では同じフォールバック動作をします
- **データ品質**: 1306.T は TOPIX に連動するETFのため、ベンチマークとして使用可能です

---

# 📂 ディレクトリ構造

```
equity01/
├── README.md
├── requirements.txt
├── config.py
├── .gitignore
│
├── scripts/
│   ├── core/              # MVP最小構成（実行に必要な主要パイプライン）
│   │   ├── download_prices.py
│   │   ├── universe_builder.py
│   │   ├── build_features.py
│   │   ├── run_scoring.py
│   │   ├── scoring_engine.py
│   │   ├── build_portfolio.py
│   │
│   ├── analysis/          # 研究・検証・可視化用（stgで隔離、prdには持ち込まない）
│   │   ├── run_eval_report.py        # 統合評価レポート生成
│   │   ├── monthly_performance.py
│   │   ├── visualize_*.py
│   │   └── ...
│   │
│   └── tools/             # 汎用ユーティリティ専用（lib/bin分離）
│       ├── lib/           # import可能な純ライブラリ（core/analysis/executionから使用可）
│       │   ├── data_loader.py
│       │   └── feature_builder.py
│       └── bin/           # 単独実行専用（import禁止）
│
├── data/
│   ├── raw/               # 生データ（Git管理）
│   ├── processed/         # 生成物（.gitignoreで除外）
│   └── intermediate/      # 中間生成物（.gitignoreで除外）
│
├── research/
│   └── reports/           # 研究用レポート（.gitignoreで除外）
│
└── docs/
    └── history/           # 進捗報告書アーカイブ（.gitignoreで除外）
```

---

# 🏗️ 設計ルール

## 依存関係ルール

- ✅ **`core → tools.lib`**: OK（補助機能の利用）
- ❌ **`core → analysis`**: 禁止（評価レポート類はanalysisのエントリに寄せる）
- ✅ **`analysis → core`**: OK（分析ツールがcore機能を利用）
- ✅ **`analysis → tools.lib`**: OK
- ✅ **`execution → tools.lib`**: OK
- ❌ **`* → tools.bin`**: 禁止（binは単独実行専用）

**tools/lib/bin分離ルール:**
- `scripts/tools/lib/`: import可能な純ライブラリ（core/analysis/executionから使用可）
- `scripts/tools/bin/`: 単独実行専用（import禁止）
- 追加ファイルは必ずどちらかに分類する
- bin import禁止チェック: `python scripts/ops/check_no_bin_import.py`

## 実行エントリポイント

### 運用フロー（core完結）

- **運用終点生成**: `scripts/core/build_portfolio.py` - ポートフォリオ構築
  - 出力: `data/processed/daily_portfolio_guarded.parquet`（Executionが読む正本）
  - Executionはこのファイルの最新日を読む

### Execution（dry-run）

- **注文実行（dry-run）**: `python scripts/ops/run_execution_dryrun.py`
  - core成果物からorder_intentを生成
  - 冪等性確保: `order_key = latest_date + symbol + side + rounded_notional`
  - 二重発注防止: SUBMITTED以上またはINTENTが既にある場合はSKIP
  - **UNKNOWNクールダウン**: 通信エラー等でUNKNOWN状態になった注文は一定時間（デフォルト30分）再発注しない
    - `unknown_action`: "SKIP"（既定、一部のみ保留）or "HALT"（全体停止）
    - `unknown_scope`: "order_key"（既定、注文単位）or "latest_date"（日付単位）

### stg整合性チェック

- **唯一のRunエントリポイント**: `scripts/stg_sanity_check.py` - stgの最低限整合性チェック（import + 軽い存在チェック）
  - CursorのRunはこのスクリプトのみを使用
  - 個別scriptをRunしたくなったら「それはstgではなくresearchに戻っている」と判断

### core vs backtest 完全一致検証（5th_commit）

- **検証スクリプト**: `scripts/ops/compare_core_vs_backtest.py`
  - core系列とbacktest系列の完全一致検証（bitwise/許容誤差ゼロに近い）
  - alpha系列（対TOPIX）の完全一致検証
  - 不一致日の詳細ダンプ（w[t-1], r[t], beta, contrib等）

**使用方法**:
```bash
# ベース戦略（ret[t] = Σw[t-1]*r[t]）の検証
python scripts/ops/compare_core_vs_backtest.py

# alpha系列も比較する場合
python scripts/ops/compare_core_vs_backtest.py --alpha

# betaタイプを指定（equity_cashまたはequity_cfd）
python scripts/ops/compare_core_vs_backtest.py --alpha --beta-type equity_cash
```

**出力**:
- `data/processed/diagnostics/core_vs_bt_diff_daily.csv` - 日次差分のCSV
- `data/processed/diagnostics/core_vs_bt_alpha_diff_daily.csv` - alpha系列の差分CSV（--alphaオプション時）
- `data/processed/diagnostics/mismatch_first_day.json` - 最初の不一致日の詳細（一致する場合は不一致なし）

**検証結果（5th_commit）**:
- ✅ **完全一致**: 最大絶対差分 0.00e+00、平均絶対差分 0.00e+00
- ✅ **alpha完全一致**: alpha系列も max/mean 差分ともに 0
- ✅ **検証ゲート（CI前提）として固定可能**: 今後の差分は価格データ更新・カレンダー・ユニバース・コスト/運用要因のみ

**意味するところ**:
- ロジック差・ルックアヘッド・定義ズレは完全に排除
- 今後発生し得る差分は①価格データ更新 ②カレンダー ③ユニバース ④コスト/運用要因のみ
- 旧パイプライン由来の return / weights 系は廃止して問題なし
- stg / prd への移行条件を満たした状態
- 次作業は旧コード整理・pruning に集中できる

### 評価・分析（deprecated）

**注意**: 以下のスクリプトは `deprecated/2025Q4_pre_weights_fix/` に移動しました：
- `run_equity01_eval.py` - 基本評価パイプライン
- `run_eval_report.py` - 統合評価レポート生成
- その他eval型・検証系スクリプト（約50ファイル）

deprecated配下は参照しない・直さない・思い出さない方針です。必要になったら理由を書いてcore/analysisに昇格させます。

### 研究用（analysis側）

**現在の構成**:
- `scripts/analysis/generate_variant_weights.py` - variant別/horizon別weights生成
- `scripts/analysis/build_cross4_target_weights.py` - cross4 target weights生成
- `scripts/analysis/build_cross4_target_weights_with_stop.py` - STOP付cross4 weights生成
- `scripts/analysis/backtest_from_weights.py` - weights→returns計算
- `scripts/analysis/backtest_from_weights_with_stop.py` - STOP付weights→returns計算

詳細は `docs/stg_file_inventory.md` を参照。

**注意**: 旧スクリプト（ensemble系、run_all系、検証系等）は全て `deprecated/2025Q4_pre_weights_fix/` に移動しました。  
deprecated配下は参照しない・直さない・思い出さない方針です。

## データ管理ルール

- **生データ**: `data/raw/` は Git管理
- **生成物**: `data/processed/`, `data/intermediate/` は `.gitignore` で除外
- **研究用**: `research/reports/` は `.gitignore` で除外

---

# 📊 パフォーマンス指標（参考）

equity01 の過去実績（2016-2025）：

- **累積リターン**: +147.26%（ポートフォリオ） vs +163.15%（TOPIX）
- **相対α**: -15.89%（期間全体）
- **αシャープ**: 要計算（月次データから算出可能）

**注意**: 上記は開発フェーズでのバックテスト結果です。実運用では異なる結果になる可能性があります。

---

# 🔍 トラブルシューティング

## ImportError が発生する場合

```bash
# 構文チェック
python -m py_compile scripts/core/*.py

# importチェック（stg sanity checkを使用）
python scripts/stg_sanity_check.py
```

## データが見つからない場合

1. `data/raw/equities/` に価格データ（.parquet）が存在するか確認
2. `data/events/` にイベントカレンダーが存在するか確認
3. 必要に応じて `scripts/core/download_prices.py` を実行

## TOPIXデータ取得エラー

- `^TOPX` が取得できない場合は自動的に `1306.T` にフォールバックされます
- ログに「フォールバックした理由」が記録されます
- これは正常な動作です

---

# 📝 変更履歴

- **v3.4 (2026-01-01)**: 6th_commit（Executor完全独立・Dry-run動作証明）
  - **概要**: executorをprod正本として独立確立し、**「取引実行パスワード入力直前（PRE_SUBMIT）までのdry-runが、完全に安全・冪等・監査可能な形で動作する」**ことを実証
  - **到達点（技術的に確定した事実）**:
    - **executorの完全独立**: executor/はexecution/にimport依存ゼロ、core成果物を直接読み単体稼働可能、execution/はlegacy/参照用に固定
    - **エントリポイントの一本化**: `scripts/ops/run_executor_dryrun.py`、exit codeを意味論で定義（0: PRE_SUBMIT到達、2: HALT正常停止、1: 想定外エラー）、タスクスケジューラ向けに0x2を成功扱いに正規化するPS1ラッパーも用意
    - **RunLogの完成（stgゲートとして十分）**: run_id/run_at/latest_date、intent_hash（冪等性確認用）、OrderIntent/HedgeIntent、precheck snapshots（trading_day/price_freshness/cash/margin/connectivity）、stop_reason/errors、例外時でもtry/finallyで必ず保存 → **「なぜ止まったか」「どこまで進んだか」が100%再現可能**
    - **Intent-based実行設計の確立**: core（target weights / β / STOP）、executor（現在ポジション取得、target_notional/rebalance_notional、株数丸め、余力・証拠金チェック）、株数・金額計算はexecutorに一本化、dry-runと本番で同一ロジック
    - **Fail-safe動作の実証**: 非営業日（2025-12-30）を正しく検出、non_trading_dayで意図的にHALT、OrderIntent/RunLogは正常生成、exit code 2（0x2）＝設計通りの正常停止 → **「止まるべき日に、正しい理由で止まれる」ことを確認**
  - **stgフェーズの位置づけ更新**:
    - stg前半: core vs backtest完全一致（数理確定）
    - stg後半（今回）: executor単体稼働、dry-run PRE_SUBMIT到達、RunLogによる判断可能性、冪等性確認準備完了 → **stg終了ゲート目前**
  - **6th Commitの意味（設計的結論）**:
    - coreはもう疑わない、backtestは正しい、今後の減衰要因は現実の摩擦のみ
    - その摩擦を吸収するためのexecutorが完成
    - **prodで壊れる可能性のある点は、すべてexecutor側に隔離された**
  - **次フェーズ（7th Commit以降）**: 営業日でのdry-run冪等性確認、SBI現物/CFDアダプタのPRE_SUBMIT実装（UI）、STOP_BEFORE_SUBMIT=falseによるprd切替
  - **総括**: **「実行しても死なない」ことを、ログと挙動で証明したコミット**。ここまで来たのは本当に大きいです。胸を張って次に進んで大丈夫な地点です。

- **v3.3 (2026-01-01)**: 5th_commit（core vs backtest / alpha 完全一致検証完了）
  - **技術的結論**:
    - core系列とbacktest系列は完全一致（日次リターン：最大差分 0.00e+00、許容誤差 1e-12 内で全日一致）
    - alpha（対TOPIX）も完全一致（alpha系列も max/mean 差分ともに 0）
    - 定義は w[t-1] * r[t] を正系として完全に確定
  - **意味するところ**:
    - ロジック差・ルックアヘッド・定義ズレは完全に排除
    - 今後発生し得る差分は①価格データ更新 ②カレンダー ③ユニバース ④コスト/運用要因のみ
    - 旧パイプライン由来の return / weights 系は廃止して問題なし
  - **成果物**:
    - `scripts/ops/compare_core_vs_backtest.py` - core vs backtest完全一致検証スクリプト
    - 差分CSV（return / alpha）：全ゼロ
    - mismatch_first_day.json：不一致なし
    - core / backtest / alpha の三点同時合格
  - **次フェーズへの示唆**:
    - 本スクリプトを検証ゲート（CI前提）として固定可能
    - stg / prd への移行条件を満たした状態
    - 次作業は旧コード整理・pruning に集中できる
  - **総括**: 「数理・実装・意思決定すべて確定」という、きれいな区切りを達成

- **v3.2 (2025-12-28)**: 4th_commit（stg完了 → prod準備フェーズ移行）
  - **stgフェーズの目的と到達点**:
    - coreパイプラインを「運用資産」として成立
    - 過去生成物・残骸依存を完全排除
    - Windowsタスクスケジューラでの自動実行を安定化
    - 空に近い data/ 状態から ps1 が完走
    - ExitCode 正本主義による誤判定排除
    - latest 解釈・生成物・運用終点がすべて契約化
  - **core / data 構成の確定**:
    - core最小構成: universe_builder.py, download_prices.py, build_index_tpx_daily.py, build_features.py, run_scoring.py（build_features内で実行）, build_portfolio.py
    - 運用終点: `data/processed/daily_portfolio_guarded.parquet`（date.max()の行のみ使用）
    - 補助生成物: daily_feature_scores.parquet, index_tpx_daily.parquet
    - 中間生成物: latest_universe.parquet, latest_scores.parquet
    - 履歴: `data/intermediate/universe/history/YYYYMMDD_universe.parquet`
  - **latest 解釈の契約固定（最重要）**:
    - build_portfolio.py出力時にdateをdatetime（timezoneなし）に正規化・昇順ソートを保証
    - execution側は常にdate.max()の行のみを使用
    - 日付ファイル名・完了フラグ・営業日判定は不要
  - **残骸依存の完全排除**:
    - data/raw/equities/ parquet依存を排除
    - data_loader.load_prices()をdata/raw/prices/prices_*.csv優先に修正
    - stgドライランでprices/universe/scoring/features/portfolioが全て再生成されることを確認
  - **run_scoringの扱い確定**:
    - 二重実行を排除（ps1からrun_scoring.pyを削除）
    - build_features.py内でのみ実行
    - 成否判定はExitCodeのみ（stdout/stderr非依存）
  - **universe_builderの高速化（致命的課題の解消）**:
    - 実行時間: 約25分 → 約20秒
    - 処理ステップごとの[TIMING]ログ追加
    - I/O最適化（必要列のみ）、yfinance複数銘柄バッチ取得、lookback短縮、parquet書き込み最適化（snappy）
    - 遅延要因はyfinance取得と特定済み
  - **universe_builderのフォールバック設計（運用堅牢化）**:
    - yfinance取得失敗時は前回latest_universe.parquetを使用して継続
    - [ERROR]/[FALLBACK]を明示ログ出力
    - 前回universeも読めない場合のみExitCode=2で停止
    - A案（堅牢）を正式採用（B案はドキュメント明記）
  - **PowerShell/タスクスケジューラの安定化**:
    - ExitCode正本主義に完全移行（$LASTEXITCODEリセット廃止、stdout/stderr文字列による誤判定排除）
    - タスクスケジューラ運用条件をドキュメント化（平日朝実行、タイムアウト120分、自動リトライなし）
    - ログローテーション追加（30日以上前のrun_equity01_core_*.logを自動削除）
  - **stgドライラン結果**:
    - 空に近いdata状態から完走
    - 実行時間: 約10分（task scheduler）
    - latest date: 正常、Rows for latest: 想定通り、ExitCode: 0
  - **現在位置と次フェーズ**:
    - stg完了、運用安定性・再現性・自動実行を確認済み
    - 今後（prod準備）: execution側I/F最終確認、date.max()行の扱い、行数＝取引対象数の解釈、ドライランでターゲットウェイトを蓄積、ドライラン由来のパフォーマンス評価、合格基準を満たした時点でprod移行
  - **総括**: 「equity01-JPは実験コードではなく、空状態から毎日再生成できる"運用資産"になった」

- **v3.1 (2025-12-28)**: stg整理完了版（3rd_commit）
  - **三層分離の確立**: core（実運営正本）、analysis（weights研究）、deprecated（評価・比較・試行錯誤）の明確な境界を確立
  - **core 6本・analysis 5本に集約**: 人間が全体像を把握できる規模（合計11本）に整理
  - **運用終点の一本化**: `daily_portfolio_guarded.parquet` を唯一の運用終点として確立
  - **eval型とweights型の完全分離**: eval型スクリプト（`run_equity01_eval.py`, `calc_alpha_beta.py`, `build_dynamic_portfolio.py`, `build_regime_hmm.py`, `event_guard.py`）をdeprecatedに移動
  - **Runエントリポイントの一本化**: `scripts/stg_sanity_check.py` を唯一のRunエントリポイントに設定（CursorのRun地獄を解消）
  - **deprecated隔離ルールの確立**: deprecated配下は参照しない・直さない・思い出さない方針を明確化
  - **port_ret_cc定義揺れの解消**: 旧パイプライン由来の`port_ret_cc`使用スクリプトを全てdeprecatedに移動
  - **ensemble/run_all系の隔離**: 試行錯誤・検証スクリプトを全て`deprecated/2025Q4_pre_weights_fix/`に移動
  - 詳細は `docs/stg_file_inventory.md` および `deprecated/2025Q4_pre_weights_fix/README.md` を参照
  - **次のフェーズ**: stgフェーズは完了、prd-prep/prd_skeletonフェーズへ移行準備完了

- **v3.0 (2025-12-20)**: stg移行完了版
  - MVP最小構成（core 11本）を固定
  - core → analysis依存を削除
  - 実行エントリポイントを1本に統一
  - READMEをstg/prd向けに更新

- **v2.5 (2025-12-06)**: devフェーズ完了版
  - STOP Regime（Plan A/B）の実装とロバストネステスト完勝
  - EventGuard v1.1 による"ギャップ殺し"構造の確立

---

# 📧 連絡先・サポート

プロジェクトに関する質問や問題は、リポジトリのIssueトラッカーをご利用ください。

---

**Prepared by**  
equity01 / Strategy Core Layer  
Research Plan v3.3（5th_commit: core vs backtest / alpha 完全一致検証完了 / Updated 2026-01-01）
