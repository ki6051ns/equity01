# ファイル分類ルール（仕分け方針）

## 概要

scripts/ 配下の全ファイルを、実運用MVPと研究・探索・別プロジェクトに明確に分離するための分類ルールです。

---

## 分類カテゴリ

### KEEP_CORE

**定義:**
- prdで日次実行される
- STOP / cross4 / EventGuard / scoring / portfolio 構築に直結
- `scripts/core/run_equity01_eval.py` から到達可能

**基準:**
1. `scripts/core/run_equity01_eval.py` から直接/間接的に呼ばれる
2. 日次実行パイプラインに必要なファイル
3. 生成物が他のcore処理に依存される
4. **coreではじまりcoreで終わる**（ロジックはcore外へ出さない）

**例:**
- `scripts/core/run_equity01_eval.py` - 実行入口
- `scripts/core/build_features.py` - 特徴量構築
- `scripts/core/build_portfolio.py` - ポートフォリオ構築
- `scripts/core/scoring_engine.py` - スコアリングエンジン
- `scripts/tools/build_index_tpx_daily.py` - TOPIXデータ構築（coreから呼ばれる）

---

### KEEP_STG_ANALYSIS

**定義:**
- stgレビュー・採用判断に必要（検証/評価レポート）
- 日次・週次のモニタリングや採用判断に必要
- STOPロバストネス、cross4評価、統合レポート

**基準:**
1. `eval_stop_regimes*.py` など、STOP採用可否を支える検証
2. `run_eval_report.py` など、統合評価レポート
3. `ensemble_variant_cross4.py` など、運用に近いアンサンブル生成
4. analysis側だが、stgレビューで必須

**例:**
- `scripts/analysis/run_eval_report.py` - 統合評価レポート
- `scripts/analysis/eval_stop_regimes.py` - STOP条件評価
- `scripts/analysis/eval_stop_regimes_robustness.py` - STOP条件ロバストネステスト
- `scripts/analysis/ensemble_variant_cross4.py` - cross4生成（運用に近い）

---

### ARCHIVE_RESEARCH

**定義:**
- 研究・可視化・実験（残してもよいが運用から分離）
- variant探索、ラダー/非ラダー検証、ホライゾン/アンサンブル実験

**基準:**
1. 再現性が低い・実運用から遠い
2. 比較実験の残骸
3. 可視化用・古い仮説用
4. `run_all_*`, `ensemble_*`（cross4以外）, 可視化・比較系

**例:**
- `scripts/analysis/run_all_*.py` - variant探索用バックテスト
- `scripts/analysis/ensemble_*.py`（cross4以外） - アンサンブル実験
- `scripts/analysis/visualize_*.py` - 可視化
- `scripts/analysis/horizon_ensemble.py` - ホライゾンアンサンブル基盤（研究用）

---

### QUARANTINE_OTHER

**定義:**
- parity / strategy-of-strategies / dynamic_portfolio 系
- equity01の運用MVPでは使わない

**基準:**
1. equity01の運用MVPではない
2. `dynamic_portfolio` 系など、別系統のプロジェクト
3. cross4/STOPの運用ラインとは別系統

**例:**
- `scripts/core/build_dynamic_portfolio.py` - 動的ポートフォリオ構築（parity用）
- `scripts/analysis/dynamic_portfolio_performance.py` - 動的ポートフォリオパフォーマンス（parity用）
- `scripts/analysis/example_dynamic_allocation.py` - 動的配分使用例（parity用）

---

### ARCHIVE_DEPRECATED

**定義:**
- 廃止された実装（使用されていない）
- 履歴として残している

**基準:**
1. 旧実装で、現在は使用されていない
2. 新しい実装に移行済み
3. 削除しても問題ないが、履歴として残している

**例:**
- `archive/core_deprecated/scoring_engine_variants.py` - 旧scoring_engine実装

---

## 分類判断フロー

### ステップ1: 実行エントリからの到達可能性確認

```
scripts/core/run_equity01_eval.py
  → KEEP_CORE
```

### ステップ2: 依存関係の確認

- **core → analysis**: ❌ 禁止
- **analysis → core**: ✅ OK（analysisがcore生成物を読む）
- **core → tools**: ✅ OK
- **analysis → tools**: ✅ OK

### ステップ3: パイプライン依存図での位置確認

`docs/pipeline_graph.md` を参照し、以下のいずれに該当するか確認：

1. **Coreフロー内**: KEEP_CORE
2. **Analysisフロー（検証・評価）**: KEEP_STG_ANALYSIS
3. **Analysisフロー（研究・実験）**: ARCHIVE_RESEARCH
4. **別系統（parity等）**: QUARANTINE_OTHER

---

## 特別ルール

### 1. scoring系（最重要）

**運用固定:**
- `scripts/core/run_scoring.py` / `scripts/core/scoring_engine.py` は運用固定
- variant探索でcoreコードを変更してはいけない

**探索用:**
- `scripts/analysis/scoring_variants.py` に分離
- coreに反映するのは config変更のみ

### 2. horizon / ensemble

**ensemble_variant_cross4.py:**
- KEEP_STG_ANALYSIS（運用に近い分析として）

**horizon_ensemble.py:**
- ARCHIVE_RESEARCH（共通ライブラリとして研究用）

**注意:**
- STOP / cross4 が動けば prdは成立する前提で整理

### 3. build_regime_hmm.py

**位置:**
- `scripts/core/build_regime_hmm.py` に配置されているが、STOP検証用

**分類:**
- KEEP_STG_ANALYSIS（stgレビューで必要）

**理由:**
- STOP検証の前段階として必要
- ただし、coreフローとは別系統（analysis側で使用）

---

## 分類根拠の記録方法

`docs/file_inventory.csv` には以下の情報を記録：

- **path**: ファイルパス
- **category**: 分類カテゴリ（KEEP_CORE / KEEP_STG_ANALYSIS / ARCHIVE_RESEARCH / QUARANTINE_OTHER / ARCHIVE_DEPRECATED）
- **why**: 分類根拠（依存図リンク＋参照元）
- **inputs**: 入力parquetファイル
- **outputs**: 出力parquetファイル
- **referenced_by**: 参照元スクリプト

---

## 例外処理

### 境界ケースの判断

**build_regime_hmm.py（scripts/core/ にあるがKEEP_STG_ANALYSIS）:**
- core/ に配置されているが、STOP検証用のため KEEP_STG_ANALYSIS
- 将来的に `scripts/analysis/` に移動することも検討

**ensemble_variant_cross4.py（scripts/analysis/ にあるがKEEP_STG_ANALYSIS）:**
- analysis/ に配置されているが、運用に近い分析のため KEEP_STG_ANALYSIS
- eval_stop_regimes*.py から参照される

---

## 確認事項

分類後、以下を確認：

1. **coreではじまりcoreで終わる**: coreフローが独立しているか
2. **analysisはcore生成物を読むだけ**: analysis側がcore生成物に書き戻していないか
3. **variant探索でcoreを触らない**: coreコードを変更せずにvariant探索が可能か

