# 危険ゾーンの保護ルール

## 概要

`scripts/core/run_scoring.py` と `scripts/core/scoring_engine.py` は運用固定（変更禁止）です。variant探索では触らない。

---

## 運用固定（変更禁止）

### scripts/core/run_scoring.py

**状態:**
- 運用固定（変更禁止）
- variant探索でcoreコードを変更してはいけない

**参照:**
- `docs/core_unification.md` - core統合記録
- `docs/variant_exploration_rules.md` - variant探索ルール

### scripts/core/scoring_engine.py

**状態:**
- 運用固定（変更禁止）
- variant探索でcoreコードを変更してはいけない

**参照:**
- `docs/core_unification.md` - core統合記録
- `docs/variant_exploration_rules.md` - variant探索ルール

---

## 変更が必要な場合の回帰テスト

### 回帰テスト要件

触る場合は **「変更前後で daily_portfolio_guarded の列/意味が変わらないこと」** を回帰テストに入れる。

**回帰テスト項目:**
1. **列の確認**
   - `daily_portfolio_guarded.parquet` の列が変更前後で同じであること
   - 必須カラム（`date`, `symbol`, `weight`）が存在すること

2. **意味の確認**
   - `weight` 列の意味が変更前後で同じであること
   - `weight` の合計が1.0であること（または仕様通り）

3. **データ整合性の確認**
   - 0やNaNや重複がないこと
   - 最新日が存在すること

**回帰テストスクリプト:**
- `scripts/tools/check_target_weights.py` を使用

**実行例:**
```bash
# 変更前
python scripts/core/build_portfolio.py
python scripts/tools/check_target_weights.py > before.txt

# 変更後
python scripts/core/build_portfolio.py
python scripts/tools/check_target_weights.py > after.txt

# 比較
diff before.txt after.txt
```

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
   - `daily_portfolio_guarded.parquet` の列/意味が変わらないこと

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

## 参照

- `docs/variant_exploration_rules.md` - variant探索ルール
- `docs/core_unification.md` - core統合記録
- `docs/classification_rules.md` - ファイル分類ルール

