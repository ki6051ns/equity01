# scripts/ 配下ファイル統合整理 実施サマリ

## 実施日
2025-01-XX

## 実施内容

### 1. core/scoring_engine.py の統合

**問題:**
- `equity01/core/scoring_engine.py`（variant探索用）と `scripts/core/scoring_engine.py`（運用MVP用）が共存していた
- `scripts/core/` 配下のファイルが `from core.scoring_engine import ...` としていたため、どちらが使われるか不明確だった

**解決策:**
1. `core/scoring_engine.py` の variant探索機能を `scripts/analysis/scoring_variants.py` に分離
2. `scripts/core/scoring_engine.py` を運用MVPとして統一
3. `core/scoring_engine.py` を `archive/core_deprecated/scoring_engine_variants.py` に移動（DEPRECATEDコメント付与）
4. `scripts/core/` 配下のファイルのimportパスを `from scripts.core.scoring_engine import ...` に統一

### 2. 実施した変更

#### ファイル移動
- `core/scoring_engine.py` → `archive/core_deprecated/scoring_engine_variants.py`
- `core/__init__.py` → `archive/core_deprecated/__init__.py`

#### 新規作成
- `scripts/analysis/scoring_variants.py`（variant探索用の新実装）
- `archive/core_deprecated/README.md`（アーカイブ理由の説明）

#### importパス修正
以下のファイルで `from core.xxx import ...` を `from scripts.core.xxx import ...` に変更：

- `scripts/core/build_features.py`
  - `from scripts.core.scoring_engine import compute_scores_all, _zscore`
  - `from scripts.tools import data_loader`

- `scripts/core/build_portfolio.py`
  - `from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio`
  - `from scripts.core.event_guard import EventGuard`

- `scripts/core/run_scoring.py`
  - `from scripts.core.scoring_engine import run_from_config`

- `scripts/core/run_equity01_eval.py`
  - `from scripts.tools.build_index_tpx_daily import main as build_index_main`
  - `from scripts.core.calc_alpha_beta import main as calc_alpha_main`

#### `scripts/core/scoring_engine.py` の修正
- `_zscore` 関数をモジュールレベルで定義（`build_features.py` から使用されるため）

---

## 統合後の構造

### 運用MVP（scripts/core/）
- `scripts/core/scoring_engine.py` - 運用固定のスコアリング実装
  - `ScoringEngineConfig`
  - `build_daily_portfolio`
  - `compute_scores_all`（基本版：z_lin, rank_only のみ）
  - `run_from_config`
  - `_zscore`（ヘルパー関数）

### variant探索（scripts/analysis/）
- `scripts/analysis/scoring_variants.py` - variant探索用の実装
  - `SCORING_VARIANTS` 辞書
  - `compute_scores_all_variants`（全variant計算）

### アーカイブ（archive/core_deprecated/）
- `archive/core_deprecated/scoring_engine_variants.py` - 旧実装（DEPRECATED）
- `archive/core_deprecated/README.md` - アーカイブ理由の説明

---

## 成果

### 1. coreを1か所・1実装に統一
- `scripts/core/scoring_engine.py` が運用MVPとして統一された
- `core/scoring_engine.py` はアーカイブされ、参照されなくなった

### 2. variant探索機能の分離
- variant探索用のコードを `scripts/analysis/scoring_variants.py` に分離
- coreを触らずにvariant探索が可能になった

### 3. importパスの明確化
- 全てのimportパスを `from scripts.core.xxx import ...` に統一
- どのファイルが使われるか明確になった

---

## 注意事項

### 1. variant探索コードの使用
variant探索が必要な場合は、`scripts/analysis/scoring_variants.py` を使用する。

```python
from scripts.analysis.scoring_variants import compute_scores_all_variants

# variant探索用のスコア計算
df = compute_scores_all_variants(df, base_col="feature_raw", group_cols=("date",))
```

### 2. 運用MVPの使用
運用側では `scripts/core/scoring_engine.py` を使用する。

```python
from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio

# 運用MVPのスコアリング
config = ScoringEngineConfig()
df_portfolio = build_daily_portfolio(df_features, config)
```

### 3. 実行方法
`scripts/core/` 配下のファイルは、`scripts/` をパスに追加してから実行する。

```bash
# プロジェクトルートから実行
python scripts/core/build_features.py
python scripts/core/run_scoring.py
python scripts/core/build_portfolio.py
python scripts/core/run_equity01_eval.py
```

---

## 回帰確認

### 確認項目

1. **importエラーの確認**
   ```bash
   python -m py_compile scripts/core/*.py
   ```

2. **実行フローの確認**
   ```bash
   # 特徴量構築
   python scripts/core/build_features.py
   
   # スコアリング
   python scripts/core/run_scoring.py
   
   # ポートフォリオ構築
   python scripts/core/build_portfolio.py
   
   # 評価パイプライン
   python scripts/core/run_equity01_eval.py
   ```

3. **STOP + cross4 の確認**
   ```bash
   # 統合評価レポート
   python scripts/analysis/run_eval_report.py
   
   # STOP検証
   python scripts/analysis/eval_stop_regimes.py
   python scripts/analysis/eval_stop_regimes_robustness.py
   ```

---

## 次のステップ

1. `docs/file_inventory.csv` の更新（core/scoring_engine.py の移動を反映）
2. `docs/cleanup_plan.md` の更新（統合手順を反映）
3. 回帰確認の実施
4. 必要に応じて、他の重複ファイルの統合を実施

