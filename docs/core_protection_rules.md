# Core保護ルール（危険ゾーン保護）

## 概要

core側の運用固定ロジックを保護し、variant探索・ladder探索・horizon探索がanalysis側で完結することを保証します。

---

## 運用固定（変更禁止）スクリプト

以下のスクリプトは**運用固定**として扱い、variant探索・ladder探索・horizon探索では触らない：

### 1. `scripts/core/run_scoring.py`

- **役割**: スコアリングエンジンの実行入口
- **保護理由**: 運用ロジックの中核。変更するとprdまで連鎖する
- **変更禁止**: variant探索・ladder探索・horizon探索では触らない

### 2. `scripts/core/scoring_engine.py`

- **役割**: スコアリングエンジンの実装（`ScoringEngineConfig`, `build_daily_portfolio`, `compute_scores_all`など）
- **保護理由**: 運用ロジックの中核。変更するとprdまで連鎖する
- **変更禁止**: variant探索・ladder探索・horizon探索では触らない

---

## 変更時の必須要件

どうしてもcore側を触る必要がある場合は、以下を満たす必要がある：

### 1. 後方互換性の維持

- **変更前後で `daily_portfolio_guarded.parquet` の列/意味が不変**
- `scripts/tools/check_target_weights.py` で検証
  - `symbol`, `weight`, `date` 列が存在
  - `sum(weight)=1`（ロングオンリー前提）
  - 0やNaNや重複がない
  - 最新日が存在

### 2. 回帰テスト

- `scripts/core/run_equity01_eval.py` が通る
- 既存の評価フローが壊れない

### 3. レビュー項目への記録

- stgのレビュー項目に差分を記録
- 変更理由・影響範囲を明確化

---

## Variant探索の正しい場所

variant探索・ladder探索・horizon探索は**analysis側で完結**させる：

### Analysis側のvariant探索

- `scripts/analysis/scoring_variants.py` - variant専用スコアリングロジック
- `scripts/analysis/generate_variant_weights.py` - variant別weights生成
- `scripts/analysis/build_cross4_target_weights.py` - variant合成

### Analysis側のladder探索

- `scripts/analysis/generate_variant_weights.py` - ladder方式のweights生成
- `docs/ladder_specification.md` - ladder仕様（ソース・オブ・トゥルース）

### Analysis側のhorizon探索

- `scripts/analysis/horizon_ensemble.py` - horizon別バックテスト
- `scripts/analysis/build_cross4_target_weights.py` - horizon合成

---

## Core→Analysis依存関係

### 許可される依存

- ✅ **analysis → core**: OK（analysisがcore生成物を読み込む）
- ✅ **analysis → tools**: OK

### 禁止される依存

- ❌ **core → analysis**: 禁止（core側はanalysis側のファイルを読み込まない）
- ❌ **analysis → core書き戻し**: 禁止（analysis生成物をcoreが読む）

**検証:**
```bash
# core→analysis依存が0であることを確認
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
# 期待結果: 0件
```

---

## 参照

- `docs/core_unification.md` - core統一の記録
- `docs/variant_exploration_rules.md` - variant探索ルール
- `docs/classification_rules.md` - ファイル分類ルール

