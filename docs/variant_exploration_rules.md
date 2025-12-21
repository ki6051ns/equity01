# variant探索ルール（core固定原則）

## 概要

variant探索は **scripts/analysis 側で完結** させ、`scripts/core/run_scoring.py` と `scripts/core/scoring_engine.py` は **運用固定（変更禁止）** です。

---

## 運用固定（変更禁止）

### scripts/core/run_scoring.py

**状態:**
- 運用固定（変更禁止）
- variant探索でcoreコードを変更してはいけない

**参照:**
- `docs/core_unification.md` - core統合記録

### scripts/core/scoring_engine.py

**状態:**
- 運用固定（変更禁止）
- variant探索でcoreコードを変更してはいけない

**参照:**
- `docs/core_unification.md` - core統合記録

---

## variant探索の分離

### scripts/analysis/scoring_variants.py

**役割:**
- variant探索用のスコアリング実装
- `scripts/core/scoring_engine.py` からvariant機能を分離

**位置づけ:**
- **ARCHIVE_RESEARCH** - variant探索用
- coreを触らずにvariant探索が可能

**参照:**
- `docs/core_unification.md` - variant探索機能の分離を説明

---

## 変更が必要な場合の手順

### 危険度の明示

変更案を出す前に、以下を必ず明示する必要があります：

1. **後方互換性**
   - 既存の運用に影響があるか
   - 既存の設定ファイルとの互換性

2. **再現性**
   - 過去の結果を再現できるか
   - 再現性に影響があるか

3. **運用影響**
   - 日次運用に影響があるか
   - エラーが発生する可能性

### 代替案の提案

変更が必要な場合、以下の代替案を必ず提案する：

1. **config化**
   - YAML/JSON設定ファイルで差し替え可能にする
   - coreコードは変更せず、設定で制御

2. **analysis側ラッパー**
   - `scripts/analysis/` 側にラッパー関数を作成
   - coreコードは変更せず、analysis側で拡張

3. **新規スクリプト**
   - `scripts/analysis/` 側に新規スクリプトを作成
   - coreコードは変更せず、別の実装を提供

---

## 分類ルール

### KEEP_CORE（運用固定）

- `scripts/core/run_scoring.py` - 運用固定
- `scripts/core/scoring_engine.py` - 運用固定

### ARCHIVE_RESEARCH（variant探索用）

- `scripts/analysis/scoring_variants.py` - variant探索用

---

## 参照

- `docs/core_unification.md` - core統合記録
- `docs/classification_rules.md` - ファイル分類ルール
- `docs/target_weights_analysis.md` - 運用終点の分析

