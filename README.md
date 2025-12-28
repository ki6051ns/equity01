# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 3.1 / Updated: 2025-12-28（stg整理完了版）**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

ALPHAERS（統合戦略）の中核である **Equity Strategy Layer** を担い、  
**透明性・説明可能性・再現性・堅牢性** を最優先に設計されています。

本バージョン（v3.1）は **stg整理完了版** であり、  
**core（実運営正本）・analysis（weights研究）・deprecated（評価・比較・試行錯誤）の三層分離** を確立し、  
**実行に必要な最小構成（core 6本・analysis 5本）** を固定しました。

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

# 4. 特徴量構築
python scripts/core/build_features.py

# 5. ポートフォリオ構築（運用終点生成）
python scripts/core/build_portfolio.py
```

### 運用終点

実行が成功すると、以下のファイルが生成されます：

- **`data/processed/daily_portfolio_guarded.parquet`** - **運用終点（Executionが読む正本）**
  - `weight` 列を含み、実運用で直接使用可能
  - 最新日（latest date）の行を読み込んで使用

**詳細:**
- `docs/core_flow_table.md` - 実行順序と入出力の詳細
- `docs/pipeline_graph.md` - パイプライン依存図

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
│   └── tools/             # 補助・ユーティリティ
│       ├── data_loader.py
│       ├── build_index_tpx_daily.py
│       └── ...
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

- ✅ **`core → tools`**: OK（補助機能の利用）
- ❌ **`core → analysis`**: 禁止（評価レポート類はanalysisのエントリに寄せる）
- ✅ **`analysis → core`**: OK（分析ツールがcore機能を利用）
- ✅ **`analysis → tools`**: OK

## 実行エントリポイント

### 運用フロー（core完結）

- **運用終点生成**: `scripts/core/build_portfolio.py` - ポートフォリオ構築
  - 出力: `data/processed/daily_portfolio_guarded.parquet`（Executionが読む正本）
  - Executionはこのファイルの最新日を読む

### stg整合性チェック

- **唯一のRunエントリポイント**: `scripts/stg_sanity_check.py` - stgの最低限整合性チェック（import + 軽い存在チェック）
  - CursorのRunはこのスクリプトのみを使用
  - 個別scriptをRunしたくなったら「それはstgではなくresearchに戻っている」と判断

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
Research Plan v3.1（stg整理完了版 / Updated 2025-12-28）
