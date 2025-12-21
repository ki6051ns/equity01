# scripts/ 配下ファイル整理 最終サマリ

## 実施日

2025-01-XX

---

## 実施内容

### 1. parquet入出力依存関係の抽出と可視化

**成果物:**
- `docs/pipeline_graph.md` - Mermaidパイプライン依存図（Core + Analysis）
- `docs/core_flow_table.md` - coreフロー表（各ステップの入出力詳細）

**成果:**
- parquetファイルの依存関係を1枚の図で可視化
- 人間レビュー可能な形式で整理

---

### 2. coreフローの始点と終点の確定

**始点:**
- `data/raw/jpx_listings/*.csv` + `data/raw/prices/*.csv` (生データ)

**終点:**
- `data/processed/daily_portfolio_guarded.parquet` - **ポートフォリオ構築の最終出力（実運用で使用）**

**結論:**
- `target_weights_latest.parquet` は存在せず、`daily_portfolio_guarded.parquet` が実質的な終点
- `daily_portfolio_guarded.parquet` には既に `weight` カラムが含まれており、実運用で直接使用可能

**詳細:**
- `docs/target_weights_analysis.md` - target_weights_latest.parquetについての分析

---

### 3. cross4 と STOP の合流点

**結論:**
- cross4 と STOP は coreフローとは別系統（analysis側）のため、coreフロー内での合流点は存在しません
- coreフローの終点（`daily_portfolio_guarded.parquet`）は、cross4/STOP とは独立して生成されます

**詳細:**
- `docs/core_flow_table.md` - cross4 と STOP の位置づけを説明

---

### 4. 仕分けルールの明文化

**成果物:**
- `docs/classification_rules.md` - ファイル分類ルールの詳細

**分類カテゴリ:**
- **KEEP_CORE**: prdで日次実行される、coreではじまりcoreで終わる
- **KEEP_STG_ANALYSIS**: stgレビュー・採用判断に必要
- **ARCHIVE_RESEARCH**: 研究・可視化・実験
- **QUARANTINE_OTHER**: parity等、別プロジェクト
- **ARCHIVE_DEPRECATED**: 廃止された実装

**成果:**
- 分類根拠を明確化
- `docs/file_inventory.csv` に依存図リンクと参照元を記録

---

### 5. variant探索でcoreを触らない構造

**対策:**
- variant探索機能を `scripts/analysis/scoring_variants.py` に分離
- `scripts/core/scoring_engine.py` は運用固定（変更禁止）
- variant探索は analysis側で完結

**詳細:**
- `docs/unified_cleanup_summary.md` - variant探索機能の分離を説明

---

### 6. 重複ファイル問題の解消

**成果物:**
- `docs/core_unification.md` - core統合記録

**実施内容:**
- `equity01/core/scoring_engine.py` を `archive/core_deprecated/scoring_engine_variants.py` に移動
- `scripts/core/scoring_engine.py` を唯一の正として統一
- importパスを `from scripts.core.xxx import ...` に統一

---

## 成果物一覧

### ドキュメント

1. **`docs/pipeline_graph.md`** - パイプライン依存図（Mermaid）
2. **`docs/core_flow_table.md`** - coreフロー表
3. **`docs/classification_rules.md`** - ファイル分類ルール
4. **`docs/core_unification.md`** - core統合記録
5. **`docs/target_weights_analysis.md`** - target_weights_latest.parquet分析
6. **`docs/file_inventory.csv`** - ファイルインベントリ（更新）
7. **`docs/unified_cleanup_summary.md`** - 統合整理の実施サマリ

### コード

1. **`scripts/analysis/scoring_variants.py`** - variant探索用の新実装
2. **`archive/core_deprecated/scoring_engine_variants.py`** - 旧実装（DEPRECATED）

---

## 確認事項（人間レビュー用チェック）

### ✅ 依存図が1枚で読める

- `docs/pipeline_graph.md` のMermaid図で、日次運用の始点→終点が追える
- CoreフローとAnalysisフローが明確に分離されている

### ✅ coreフロー表がcross4とSTOPの合流点を説明できる

- `docs/core_flow_table.md` で、cross4とSTOPがcoreフローとは別系統であることを説明

### ✅ daily_portfolio_guarded.parquetの生成コードと生成場所が確定している

- `scripts/core/build_portfolio.py` で生成
- `data/processed/daily_portfolio_guarded.parquet` に保存
- 実運用で使用可能な形式（weightカラムを含む）

### ✅ analysis側のスクリプトはcore生成物を読むだけ

- analysis側はcore生成物（parquet）を読み込む
- core生成物に書き戻さない（analysis側は読み取り専用）

---

## 次のステップ

1. **回帰確認**
   - `python scripts/core/run_equity01_eval.py` が正常に動作することを確認
   - `python scripts/analysis/run_eval_report.py` が正常に動作することを確認

2. **README.md の更新**
   - 終点（daily_portfolio_guarded.parquet）を明記
   - 実行フローの説明を更新

3. **必要に応じて追加整理**
   - 他の重複ファイルがないか確認
   - 不要なファイルのアーカイブ

