# scripts/ 配下ファイル整理計画

## 概要

equity01 の JP-stg ブランチで、scripts/ 配下の「実運用MVP」と「研究/派生/別PJ」を人間が追える形で仕分けし、整理する。

分類結果は `docs/file_inventory.csv` に記載。

---

## 分類カテゴリ

### KEEP_CORE
- **定義**: PRDまで残す運用MVP（coreから呼ばれる/日次実行に必要）
- **基準**: 
  - `core/run_equity01_eval.py` から直接/間接的に呼ばれる
  - 日次実行パイプラインに必要なファイル
  - 生成物が他のcore処理に依存される

### KEEP_STG_ANALYSIS
- **定義**: stgレビュー・採用判断に必要（検証/評価レポート）
- **基準**:
  - `eval_stop_regimes*.py` など、STOP採用可否を支える検証
  - `run_eval_report.py` など、統合評価レポート
  - `ensemble_variant_cross4.py` など、運用に近いアンサンブル生成

### ARCHIVE_RESEARCH
- **定義**: 研究・可視化・実験（残してもよいが運用から分離）
- **基準**:
  - 再現性が低い・実運用から遠い
  - 比較実験の残骸
  - 可視化用・古い仮説用

### QUARANTINE_OTHER
- **定義**: parity等、別プロジェクト・用途不明・重複
- **基準**:
  - equity01の運用MVPではない
  - `dynamic_portfolio` 系など、別系統のプロジェクト

### DELETE_CANDIDATE
- **定義**: 明確に不要（ただし削除前提は根拠必須）
- **注意**: 今回は候補出しのみ。実際の削除は別途判断。

---

## 整理手順

### フェーズ1: 現状確認（完了）

- [x] scripts/ 配下の全 .py ファイルをリストアップ
- [x] 各ファイルの依存関係（import/呼び出し）を分析
- [x] 各ファイルの入出力（parquet）を分析
- [x] 分類カテゴリに基づいて全ファイルを分類
- [x] `docs/file_inventory.csv` を作成

### フェーズ2: 移動・隔離（推奨実施順序）

#### 2.1 QUARANTINE_OTHER の隔離

**対象ファイル:**
- `core/build_dynamic_portfolio.py`
- `analysis/dynamic_portfolio_performance.py`
- `analysis/example_dynamic_allocation.py`

**作業:**
```bash
# parity ディレクトリを作成（プロジェクトルート）
mkdir -p scripts/parity

# dynamic_portfolio系を移動
mv scripts/core/build_dynamic_portfolio.py scripts/parity/
mv scripts/analysis/dynamic_portfolio_performance.py scripts/parity/
mv scripts/analysis/example_dynamic_allocation.py scripts/parity/

# READMEを追加
cat > scripts/parity/README.md << 'EOF'
# parity/ - 別プロジェクト関連

このディレクトリには、equity01 の運用MVPとは別系統のプロジェクト関連ファイルを配置しています。

## 内容

- `build_dynamic_portfolio.py`: 動的ウェイト配分ポートフォリオ構築
- `dynamic_portfolio_performance.py`: 動的ポートフォリオパフォーマンス計算
- `example_dynamic_allocation.py`: 動的配分使用例

これらは cross4/STOP の運用ラインとは別系統です。
EOF
```

**注意点:**
- `core/build_dynamic_portfolio.py` は `core/` にあるが、実際は別プロジェクト
- `analysis/` から移動するため、importパスの修正が必要になる可能性がある

#### 2.2 ARCHIVE_RESEARCH のアーカイブ

**対象ディレクトリ構造:**
```
scripts/
  research/          # 新規作成
    ensemble/        # アンサンブル実験系
    visualization/   # 可視化系
    backtest/        # バックテスト実験系
    utilities/       # ユーティリティ系
```

**移動対象ファイル:**

**ensemble系（研究・実験用アンサンブル）:**
```bash
mkdir -p scripts/research/ensemble
mv scripts/analysis/ensemble_rank_only.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zclip.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zdownbeta.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zdowncombo.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zdownvol.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zlin.py scripts/research/ensemble/
mv scripts/analysis/ensemble_zlowvol.py scripts/research/ensemble/
mv scripts/analysis/ensemble_variant_cross.py scripts/research/ensemble/
mv scripts/analysis/ensemble_variant_cross2.py scripts/research/ensemble/
mv scripts/analysis/ensemble_variant_cross3.py scripts/research/ensemble/
mv scripts/analysis/ensemble_custom_weights.py scripts/research/ensemble/
mv scripts/analysis/horizon_ensemble.py scripts/research/ensemble/
mv scripts/analysis/run_all_rank_only.py scripts/research/ensemble/
mv scripts/analysis/run_all_zclip.py scripts/research/ensemble/
mv scripts/analysis/run_all_zdownbeta.py scripts/research/ensemble/
mv scripts/analysis/run_all_zdowncombo.py scripts/research/ensemble/
mv scripts/analysis/run_all_zdownvol.py scripts/research/ensemble/
mv scripts/analysis/run_all_zlin.py scripts/research/ensemble/
mv scripts/analysis/run_all_zlowvol.py scripts/research/ensemble/
mv scripts/analysis/run_ensemble_custom_simple.py scripts/research/ensemble/
mv scripts/analysis/run_ensemble_from_existing.py scripts/research/ensemble/
mv scripts/analysis/run_single_horizon.py scripts/research/ensemble/
mv scripts/analysis/backtest_non_ladder.py scripts/research/ensemble/
```

**visualization系（可視化）:**
```bash
mkdir -p scripts/research/visualization
mv scripts/analysis/visualize_bpi.py scripts/research/visualization/
mv scripts/analysis/visualize_bpi_126d.py scripts/research/visualization/
mv scripts/analysis/visualize_inverse_etf_126d.py scripts/research/visualization/
mv scripts/analysis/visualize_regime_hmm.py scripts/research/visualization/
```

**analysis系（分析・集計）:**
```bash
mkdir -p scripts/research/analysis
mv scripts/analysis/aggregate_yearly_performance.py scripts/research/analysis/
mv scripts/analysis/rolling_relative_alpha.py scripts/research/analysis/
mv scripts/analysis/build_bpi.py scripts/research/analysis/
mv scripts/analysis/calc_bpi_126d.py scripts/research/analysis/
mv scripts/analysis/compare_ladder_vs_baseline.py scripts/research/analysis/
```

**utilities系（開発・デバッグ用）:**
```bash
mkdir -p scripts/research/utilities
mv scripts/analysis/check_h1_stats.py scripts/research/utilities/
mv scripts/analysis/check_horizon_progress.py scripts/research/utilities/
mv scripts/tools/preview_parquet.py scripts/research/utilities/
mv scripts/tools/preview_universe.py scripts/research/utilities/
mv scripts/tools/validate_listings.py scripts/research/utilities/
mv scripts/tools/calc_minimum_capital.py scripts/research/utilities/
mv scripts/tools/post_loss_analyzer.py scripts/research/utilities/
mv scripts/tools/regime_engine.py scripts/research/utilities/
mv scripts/tools/fetch_prices.py scripts/research/utilities/  # 非推奨、data_loader使用推奨
```

**注意点:**
- `analysis/horizon_ensemble.py` は多くのファイルからimportされているため、移動後にimportパスの修正が必要
- `analysis/ensemble_variant_cross4.py` は **KEEP_STG_ANALYSIS** のため、移動しない

#### 2.3 importパスの修正

移動後、以下のimportパス修正が必要：

**horizon_ensemble.py のimport修正:**
```python
# 修正前（scripts/analysis/ensemble_*.py など）
from horizon_ensemble import ...

# 修正後
from research.ensemble.horizon_ensemble import ...
# または
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]  # research/ensemble から見て2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from research.ensemble.horizon_ensemble import ...
```

**その他のimport修正:**
- `ensemble_variant_cross4.py` が `horizon_ensemble` をimportしている場合 → `research.ensemble.horizon_ensemble` に修正
- `eval_stop_regimes*.py` が `horizon_ensemble` をimportしている場合 → `research.ensemble.horizon_ensemble` に修正（ただし、eval_stop_regimes系はKEEP_STG_ANALYSISなので、必要に応じて`horizon_ensemble.py`を`analysis/`にコピーまたはシンボリックリンクを作成することも検討）

---

### フェーズ3: 整理後の確認

#### 3.1 実行確認

**core実行フローの確認:**
```bash
# 1. universe構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格取得
python scripts/core/download_prices.py

# 3. 特徴量構築
python scripts/core/build_features.py

# 4. スコアリング
python scripts/core/run_scoring.py

# 5. ポートフォリオ構築
python scripts/core/build_portfolio.py

# 6. 評価パイプライン実行
python scripts/core/run_equity01_eval.py
```

**stg分析実行フローの確認:**
```bash
# 1. cross4生成（研究用ensembleが必要な場合、research/ensemble から実行）
# 注意: ensemble_variant_cross4.py は analysis/ に残す

# 2. 統合評価レポート
python scripts/analysis/run_eval_report.py

# 3. STOP検証
python scripts/analysis/eval_stop_regimes.py
python scripts/analysis/eval_stop_regimes_robustness.py
```

#### 3.2 依存関係の確認

```bash
# importエラーのチェック
python -m py_compile scripts/core/*.py
python -m py_compile scripts/analysis/*.py
python -m py_compile scripts/tools/*.py
```

---

## 残置ファイル（KEEP_CORE / KEEP_STG_ANALYSIS）

### core/ 配下（KEEP_CORE）

**実行エントリ:**
- `run_equity01_eval.py` - 基本評価パイプライン
- `run_scoring.py` - スコアリング実行
- `build_features.py` - 特徴量構築
- `build_portfolio.py` - ポートフォリオ構築
- `universe_builder.py` - ユニバース構築
- `download_prices.py` - 価格取得

**コアライブラリ:**
- `scoring_engine.py` - スコアリングエンジン
- `calc_alpha_beta.py` - α計算
- `event_guard.py` - イベントガード

**検証関連（KEEP_STG_ANALYSIS）:**
- `build_regime_hmm.py` - レジームHMM構築

### analysis/ 配下（KEEP_STG_ANALYSIS）

**評価レポート:**
- `run_eval_report.py` - 統合評価レポート生成
- `monthly_performance.py` - 月次パフォーマンス集計

**STOP検証:**
- `eval_stop_regimes.py` - STOP条件評価
- `eval_stop_regimes_robustness.py` - STOP条件ロバストネステスト

**運用アンサンブル:**
- `ensemble_variant_cross4.py` - Variant-Cross Ensemble4（運用に近い）

### tools/ 配下（KEEP_CORE）

**データ操作:**
- `data_loader.py` - データローダー
- `build_index_tpx_daily.py` - TOPIXデータ構築
- `feature_builder.py` - 特徴量ビルダー
- `weights_cleaning.py` - ウェイトクリーニング
- `paper_trade.py` - ペーパートレード

**実運用接続（将来使用）:**
- `order_builder.py` - オーダービルダー
- `execution_simulator.py` - エクゼキューションシミュレーター
- `portfolio_optimizer.py` - ポートフォリオオプティマイザー

---

## 注意事項

### 1. ensemble_variant_cross4.py の位置

`ensemble_variant_cross4.py` は **KEEP_STG_ANALYSIS** のため `analysis/` に残す。

ただし、このファイルは `horizon_ensemble.py` をimportしている。`horizon_ensemble.py` を `research/ensemble/` に移動する場合：

- **オプションA**: `horizon_ensemble.py` を `analysis/` にもコピー（重複だが依存関係が明確）
- **オプションB**: `ensemble_variant_cross4.py` 内で `research.ensemble.horizon_ensemble` をimport（パス修正が必要）
- **オプションC**: `horizon_ensemble.py` を `scripts/` 直下に配置（共通ライブラリとして）

推奨: **オプションA** または **オプションC**

### 2. eval_stop_regimes*.py の依存関係

`eval_stop_regimes*.py` も `horizon_ensemble.py` の関数（`compute_monthly_perf`）をimportしている。

同様に、`horizon_ensemble.py` を移動する場合の対応が必要。

### 3. build_dynamic_portfolio.py の参照

`core/build_dynamic_portfolio.py` は `horizon_ensemble_rank_only.parquet` と `horizon_ensemble_variant_cross3.parquet` を参照しているが、これらは research用アンサンブルの生成物。

parityプロジェクトとして隔離する際は、必要に応じてこれらのparquetファイルも別ディレクトリに移動することを検討。

### 4. データファイルの整理

`data/processed/` 配下のparquetファイルも整理対象だが、今回は scripts/ の整理が主目的。

必要に応じて別途 `data/processed/research/` や `data/processed/parity/` を作成して移動することも検討。

---

## 実行前チェックリスト

- [ ] `docs/file_inventory.csv` の内容を確認
- [ ] 移動対象ファイルのバックアップを作成（git commit推奨）
- [ ] importパスの修正箇所をリストアップ
- [ ] テスト実行環境を準備

---

## 実行後チェックリスト

- [ ] core実行フローが正常に動作することを確認
- [ ] stg分析実行フローが正常に動作することを確認
- [ ] importエラーがないことを確認
- [ ] `docs/file_inventory.csv` を更新（移動後のパスを反映）
- [ ] README.md を更新（ディレクトリ構造の変更を反映）

---

## 参考情報

- 分類結果: `docs/file_inventory.csv`
- 実行エントリ: `scripts/core/run_equity01_eval.py`, `scripts/analysis/run_eval_report.py`
- 運用アンサンブル: `scripts/analysis/ensemble_variant_cross4.py`
- STOP検証: `scripts/analysis/eval_stop_regimes_robustness.py`

