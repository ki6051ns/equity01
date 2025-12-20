# JP-stg 整理作業サマリ

## 実施日
2025-12-20

## stg①: ディレクトリ整理 ✅

### 1. MVP最小構成の特定と固定 ✅

**core/（実行に必要な主要パイプライン）**
- `download_prices.py` - データ取得
- `universe_builder.py` - ユニバース構築
- `build_features.py` - 特徴量構築
- `run_scoring.py` / `scoring_engine.py` - スコアリング
- `build_portfolio.py` - ポートフォリオ構築
- `build_dynamic_portfolio.py` - 動的ポートフォリオ
- `event_guard.py` - EventGuard
- `build_regime_hmm.py` - STOP Regime
- `calc_alpha_beta.py` - α/β計算
- `run_equity01_eval.py` - 評価エントリ

### 2. .gitignore作成 ✅

以下の項目を除外：
- `venv/` - 仮想環境
- `__pycache__/` - Pythonキャッシュ
- `data/processed/**/*.parquet` - 生成物
- `data/processed/**/*.png` - 可視化出力
- `research/reports/**/*.png` - 研究用レポート
- `docs/history/**` - 進捗報告書アーカイブ

### 3. scripts/の分類 ✅

#### core/（MVP最小構成）
実行に必要な主要パイプラインスクリプト（11ファイル）

#### analysis/（研究・検証・可視化用）
- 一括実行スクリプト（`run_all_*.py`）
- アンサンブル実験（`ensemble_*.py`）
- 可視化（`visualize_*.py`）
- 検証・評価（`eval_*.py`, `compare_*.py`）
- 分析・集計（`aggregate_*.py`, `monthly_*.py`など）

**合計：約35ファイル**

#### tools/（補助・ユーティリティ）
- データ操作（`data_loader.py`, `fetch_prices.py`）
- プレビュー・検証（`preview_*.py`, `validate_*.py`）
- その他補助スクリプト

**合計：約15ファイル**

### 4. ディレクトリ構造の整理 ✅

- `進捗報告書/` → `docs/history/` に移動（.gitignoreに追加）
- `research/reports/` - 研究用として明示（.gitignoreで除外）

---

## stg②: import整合性修正 ✅

### 1. importエラーの特定と修正 ✅

**発見された問題:**
- `core.build_features`が`compute_scores_all`を`core.scoring_engine`からimportできない
- `core.run_scoring`が`run_from_config`を`core.scoring_engine`からimportできない

**修正内容:**
- `scoring_engine.py`に`compute_scores_all()`関数を追加
  - Z-score線形結合（`score_z_lin`）とランクベーススコア（`score_rank_only`）を計算
- `scoring_engine.py`に`run_from_config()`関数を追加
  - 設定ファイル（YAML）からスコアを計算する簡易実装

### 2. core → analysis依存の削除 ✅

**設計ルール:**
- ✅ `core → tools`: OK
- ❌ `core → analysis`: 禁止

**実施内容:**
- `run_equity01_eval.py`から`analysis/`への参照を削除
- 完全統合型評価パイプライン（月次集計・ホライゾンアンサンブル）は`analysis/run_eval_report.py`に移行予定
- `run_equity01_eval.py`はcore直下で完結する最小評価のみを提供

### 3. importパスの修正 ✅

- `run_equity01_eval.py`のimportパスを修正：
  - `tools.build_index_tpx_daily`
  - `core.calc_alpha_beta`
- 他のcore/ファイルのimportパスも確認・修正

### 4. 動作確認 ✅

- ✅ `py_compile`で構文チェック: 全ファイル成功
- ✅ `run_equity01_eval.py --help`: 正常動作
- ✅ importチェック: 主要なimportエラーを解消

---

## 現在の状態

### 完了項目
1. ✅ MVP最小構成（core 11本）を固定
2. ✅ 生成物・venv・研究レポート類を.gitignoreで隔離
3. ✅ scripts/をcore/analysis/toolsに分割
4. ✅ importの整合性を修正（主要なエラーを解消）
5. ✅ core → analysis依存を削除

### 残作業

#### 高優先度
1. **実際の実行テスト**
   - `python scripts/core/run_equity01_eval.py`を実行して、データが無くてもimportエラーが発生しないことを確認
   - データが無くて途中で止まるのはOK、ImportErrorはNG

2. **analysis/run_eval_report.pyの作成**
   - 完全統合型評価パイプライン（月次集計・ホライゾンアンサンブル）を実装
   - `run_equity01_eval.py`から参照されていた機能を移行

#### 中優先度
3. **他のcore/ファイルの実行時エラー確認**
   - `Path`のimport不足など、実行時に発生する可能性のあるエラーを確認

4. **ドキュメント更新**
   - README.mdの更新（新しいディレクトリ構造を反映）
   - 実行手順の更新

---

## ディレクトリ構造（整理後）

```
equity01/
├── README.md
├── requirements.txt
├── config.py
├── .gitignore
├── scripts/
│   ├── core/          # MVP最小構成（11ファイル）
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
│   │   └── run_equity01_eval.py  # 実行エントリポイント
│   ├── analysis/      # 研究・検証用（約35ファイル）
│   └── tools/         # 補助・ユーティリティ（約15ファイル）
├── data/
│   ├── raw/           # 生データ（Git管理）
│   ├── processed/     # 生成物（.gitignoreで除外）
│   └── intermediate/   # 中間生成物（.gitignoreで除外）
├── research/
│   └── reports/       # 研究用レポート（.gitignoreで除外）
└── docs/
    └── history/       # 進捗報告書アーカイブ（.gitignoreで除外）
```

## 設計ルール（確定）

### 依存関係ルール
- ✅ `core → tools`: OK（補助機能の利用）
- ❌ `core → analysis`: 禁止（評価レポート類はanalysisのエントリに寄せる）
- ✅ `analysis → core`: OK（分析ツールがcore機能を利用）
- ✅ `analysis → tools`: OK

### 実行エントリポイント
- **core**: `scripts/core/run_equity01_eval.py` - 基本評価パイプライン
- **analysis**: `scripts/analysis/run_eval_report.py`（作成予定）- 完全統合評価

---

## stg③: 評価の統合と運用ドキュメント ✅

### 1. scripts/analysis/run_eval_report.py の確認・修正 ✅
- 既存ファイルを確認し、importパスを修正
- coreの成果物を読み込んで月次集計・統計レポートを生成
- 出力先: `research/reports/`（git管理外）

### 2. README.md の更新 ✅
- セットアップ手順（Python/requirements、venvはgit外）
- stgでの実行方法（入口コマンド1本）
- データ配置（raw/ processed/ intermediate、git管理範囲）
- ^TOPX→1306.T フォールバック仕様（prdまで通用する仕様として明記）

### 3. stgレビュー項目テンプレートの作成 ✅
- `docs/stg_review_template.md` を作成
- 四半期レビューの土台として以下を固定化：
  - データ取得成功率
  - STOP発火率（想定: 11.8%付近）
  - ターンオーバー/売買回数（SBI配慮の観点）
  - 主要な例外ログ（フォールバック回数含む）

### 4. build_index_tpx_daily.py のdocstring更新 ✅
- フォールバック仕様をprdまで通用する形で明記
- ログ出力の監査性を強調

---

## stg移行完了 ✅

### 完了項目
1. ✅ MVP最小構成（core 11本）を固定
2. ✅ 生成物・venv・研究レポート類を.gitignoreで隔離
3. ✅ scripts/をcore/analysis/toolsに分割
4. ✅ importの整合性を修正
5. ✅ core → analysis依存を削除
6. ✅ 実行テスト成功（ImportErrorゼロ）
7. ✅ 統合評価レポート生成機能の確認
8. ✅ README.md更新（stg/prd向け）
9. ✅ stgレビュー項目テンプレート作成

### stg→prd移行準備完了
- **再現可能な実行入口**: `python scripts/core/run_equity01_eval.py`
- **設計ルール**: core → analysis依存禁止を遵守
- **運用ドキュメント**: README.md + レビューテンプレート
- **監査性**: フォールバック仕様とログ出力を明記

---

## 次のステップ（prd移行時）

1. **本番環境へのデプロイ**
   - 実行環境のセットアップ
   - データ取得の自動化（スケジューラ）

2. **モニタリング体制の構築**
   - 四半期レビューの実施
   - ログ監視の自動化

3. **継続的な改善**
   - パフォーマンス指標の追跡
   - リスク管理の強化
