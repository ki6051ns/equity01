# 人間レビュー用チェックリスト

## ✅ 確認項目

### 1. 依存図が1枚で読める

- [x] `docs/pipeline_graph.md` のMermaid図で、日次運用の始点→終点が追える
- [x] CoreフローとAnalysisフローが明確に分離されている
- [x] 各parquetファイルの生成元スクリプトが明記されている

**確認方法:**
- `docs/pipeline_graph.md` の「完全な依存図（Core + Analysis統合）」セクションを確認

---

### 2. coreフロー表がcross4とSTOPの合流点を説明できる

- [x] `docs/core_flow_table.md` で、cross4とSTOPがcoreフローとは別系統であることを説明
- [x] coreフローの終点（`daily_portfolio_guarded.parquet`）が明確

**確認方法:**
- `docs/core_flow_table.md` の「cross4 と STOP の合流点」セクションを確認

---

### 3. daily_portfolio_guarded.parquetの生成コードと生成場所が確定している

- [x] 生成元スクリプト: `scripts/core/build_portfolio.py`
- [x] 保存先: `data/processed/daily_portfolio_guarded.parquet`
- [x] 実運用で使用可能な形式（weightカラムを含む）

**確認方法:**
- `docs/core_flow_table.md` の「STEP 5: build_portfolio.py」セクションを確認
- `docs/target_weights_analysis.md` で詳細を確認

---

### 4. analysis側のスクリプトはcore生成物を読むだけ

- [x] analysis側はcore生成物（parquet）を読み込む
- [x] core生成物に書き戻さない（analysis側は読み取り専用）

**確認方法:**
- `docs/pipeline_graph.md` の「Analysisフロー」セクションを確認
- `docs/classification_rules.md` の「依存関係ルール」セクションを確認

---

### 5. coreではじまりcoreで終わる（ロジックはcore外へ出さない）

- [x] coreフローが独立している
- [x] coreからanalysisへの依存がない
- [x] variant探索機能がanalysis側に分離されている

**確認方法:**
- `docs/pipeline_graph.md` の依存図で、core→analysisのエッジがないことを確認
- `docs/unified_cleanup_summary.md` でvariant探索機能の分離を確認

---

### 6. 重複ファイル問題の解消

- [x] `equity01/core/scoring_engine.py` を `archive/core_deprecated/` に移動
- [x] `scripts/core/scoring_engine.py` を唯一の正として統一
- [x] importパスを `from scripts.core.xxx import ...` に統一

**確認方法:**
- `docs/core_unification.md` で統合記録を確認

---

### 7. core→analysis依存ゼロ

- [x] `scripts/core/**` から `scripts/analysis/**` へのimportが0件であることを確認

**確認方法:**
```bash
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
```

**結果:**
- **0件** - coreからanalysisへの依存は存在しない ✅

**結論:**
- core→analysis禁止のルールがコードで担保されている
- analysisはcore生成物（parquet）を読むだけ（書き戻し禁止）

---

## 📋 成果物確認

### ドキュメント

- [x] `docs/pipeline_graph.md` - パイプライン依存図（Mermaid）
- [x] `docs/core_flow_table.md` - coreフロー表
- [x] `docs/classification_rules.md` - ファイル分類ルール
- [x] `docs/core_unification.md` - core統合記録
- [x] `docs/target_weights_analysis.md` - target_weights_latest.parquet分析
- [x] `docs/file_inventory.csv` - ファイルインベントリ（更新）
- [x] `docs/unified_cleanup_summary.md` - 統合整理の実施サマリ
- [x] `docs/final_summary.md` - 最終サマリ

### コード

- [x] `scripts/analysis/scoring_variants.py` - variant探索用の新実装
- [x] `archive/core_deprecated/scoring_engine_variants.py` - 旧実装（DEPRECATED）

---

## 🚀 回帰確認（推奨）

### Core実行フロー

```bash
# 1. universe構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格取得
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet

# 3. 特徴量構築
python scripts/core/build_features.py

# 4. ポートフォリオ構築
python scripts/core/build_portfolio.py

# 5. 評価パイプライン実行
python scripts/core/run_equity01_eval.py
```

### Analysis実行フロー

```bash
# 1. 統合評価レポート
python scripts/analysis/run_eval_report.py

# 2. STOP検証（cross4が必要）
python scripts/analysis/ensemble_variant_cross4.py
python scripts/analysis/eval_stop_regimes.py
python scripts/analysis/eval_stop_regimes_robustness.py
```

---

## ✅ 全てのチェック項目をクリア

全ての確認項目が完了しています。

