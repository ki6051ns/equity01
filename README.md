# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 3.0 / Updated: 2025-12-20（stg移行完了版）**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

ALPHAERS（統合戦略）の中核である **Equity Strategy Layer** を担い、  
**透明性・説明可能性・再現性・堅牢性** を最優先に設計されています。

本バージョン（v3.0）は **stg移行完了版** であり、  
**実行に必要な最小構成（MVP）** を固定し、**再現可能な実行入口** を確保しました。

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

stgでの実行は **1本のコマンド** で完結します：

```bash
python scripts/core/run_equity01_eval.py
```

このコマンドで以下が順次実行されます：

1. **TOPIXインデックスデータの更新** (`build_index_tpx_daily`)
2. **ペーパートレード + 相対α計算** (`calc_alpha_beta`)
3. **Rolling相対α計算** (`rolling_relative_alpha`)

### 実行結果

実行が成功すると、以下のファイルが生成されます：

- `data/processed/index_tpx_daily.parquet` - TOPIX日次リターン
- `data/processed/paper_trade_with_alpha_beta.parquet` - ペーパートレード結果 + 相対α
- `data/processed/rolling_relative_alpha.parquet` - Rolling相対α（10/20/60/120日）

## 統合評価レポート生成（オプション）

詳細な月次集計・統計レポートを生成する場合：

```bash
python scripts/analysis/run_eval_report.py
```

**注意**: このコマンドは `core/run_equity01_eval.py` の後に実行してください。

### 出力先

- `research/reports/summary_stats.csv` - 基本統計
- `research/reports/monthly_performance.csv` - 月次パフォーマンス

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
│   │   ├── build_dynamic_portfolio.py
│   │   ├── event_guard.py
│   │   ├── build_regime_hmm.py
│   │   ├── calc_alpha_beta.py
│   │   └── run_equity01_eval.py      # 実行エントリポイント
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

- **core**: `scripts/core/run_equity01_eval.py` - 基本評価パイプライン
- **analysis**: `scripts/analysis/run_eval_report.py` - 統合評価レポート生成

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

# importチェック
python scripts/core/run_equity01_eval.py --help
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
Research Plan v3.0（stg移行完了版 / Updated 2025-12-20）
