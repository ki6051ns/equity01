# cross4 weights版検証実行ガイド

## 概要

weights版cross4と既存return合成cross4の一致検証を実行し、PASS/FAILを記録する手順です。

---

## 実行方法

### 一括実行（推奨）

すべてのステップ（①→②→③→④）を自動実行します：

```bash
python scripts/analysis/run_cross4_weights_verification.py
```

**オプション:**
- `--step {1,2,3,4}`: 特定のステップのみ実行
- `--skip-weights`: ① weights生成をスキップ（既に生成済みの場合）
- `--horizons HORIZONS ...`: 実行するhorizonを指定（デフォルト: 1 5 10 60 90 120）
- `--variants {rank,zdownvol} ...`: 実行するvariantを指定（デフォルト: rank zdownvol）

**例:**
```bash
# すべて実行
python scripts/analysis/run_cross4_weights_verification.py

# ②以降のみ実行（weightsは既に生成済み）
python scripts/analysis/run_cross4_weights_verification.py --skip-weights

# 特定のステップのみ実行
python scripts/analysis/run_cross4_weights_verification.py --step 4

# 特定のhorizonのみ実行
python scripts/analysis/run_cross4_weights_verification.py --horizons 60 90 120
```

---

### 個別実行

詳細を確認しながら実行する場合：

以下の順序で実行してください：

### ① variant別/horizon別のweightsを生成

```bash
# rank_only variant
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 120 --ladder ladder

# zdownvol variant
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 120 --ladder ladder
```

**出力:**
- `data/processed/weights/h{H}_{ladder}_{variant}.parquet`

### ② cross4 target weightsを生成

```bash
python scripts/analysis/build_cross4_target_weights.py
```

**出力:**
- `data/processed/weights/cross4_target_weights.parquet`（全期間）
- `data/processed/weights/cross4_target_weights_latest.parquet`（最新日のみ）

### ③ weights→returnsを計算

```bash
python scripts/analysis/backtest_from_weights.py
```

**出力:**
- `data/processed/weights_bt/cross4_from_weights.parquet`

### ④ 一致検証

```bash
python scripts/analysis/verify_cross4_equivalence.py
```

**出力:**
- `research/reports/cross4_weights_equivalence.csv`（検証結果）
- `research/reports/cross4_weights_equivalence_detail.parquet`（詳細差分）
- `research/reports/cross4_weights_equivalence_top20_diff.csv`（差分が大きい日top20）
- `research/reports/cross4_weights_top_diff_date_{YYYYMMDD}.csv`（差分最大日のweights上位30銘柄、FAIL時）

---

## PASS/FAIL判定

### 検証指標

- `mean_abs_diff_daily`: 日次差分の平均絶対値
- `max_abs_diff_daily`: 日次差分の最大絶対値
- `cumret_diff_last`: 累積リターン差分（最終日）

**許容誤差:** `1e-8`

**判定:**
- すべての指標が許容誤差以内 → **PASS**
- いずれかの指標が許容誤差を超える → **FAIL**

### PASS時の記録

PASSした場合：

1. `research/reports/cross4_weights_equivalence.csv` を確認
2. `docs/old_analysis_deprecation.md` の Phase 1 を完了として記録
3. Phase 2（参照先の移行）に進む

---

## FAIL時の原因特定手順

FAILした場合、以下の手順で原因を特定します：

### 1. 差分が大きい日を確認

```bash
# top20 diff CSVを確認
cat research/reports/cross4_weights_equivalence_top20_diff.csv
```

**確認ポイント:**
- 差分が大きい日は特定の日付に集中しているか
- ランダムに散らばっているか

### 2. 原因の切り分け

#### A. 日付アライメントの問題

**症状:**
- 差分が大きい日が特定の日付（例: 月末、月初）に集中
- `trade_date`列の日付が一致していない

**確認方法:**
- `research/reports/cross4_weights_equivalence_detail.parquet` を読み込み
- `trade_date`列を比較（旧方式 vs 新方式）

**対応:**
- `backtest_from_weights.py` の日付処理を確認
- weightsファイルの日付が全営業日を含むか確認（ladder方式）

#### B. 翌日リターンの取り方の問題

**症状:**
- 差分が全体的に大きい（特定の日付に集中しない）
- `port_ret_cc`の差分が一貫して大きい

**確認方法:**
- `research/reports/cross4_weights_equivalence_detail.parquet` を読み込み
- 旧方式と新方式の`port_ret_cc`を比較

**対応:**
- `backtest_from_weights.py` のリターン計算ロジックを確認
  - 当日weightsで翌営業日のリターンを取得しているか
  - リターン計算式: `port_ret_cc = (weights_aligned * rets_aligned).sum()`

#### C. 欠損日の扱いの問題

**症状:**
- 差分が大きい日が特定のパターン（例: 決算日、祝日後）に集中
- weightsファイルに欠損日がある

**確認方法:**
- `research/reports/cross4_weights_top_diff_date_{YYYYMMDD}.csv` を確認
- weightsファイルの日付リストを確認（全営業日を含むか）

**対応:**
- `generate_variant_weights.py` のladder実装を確認
  - データがない日でも、キューがあれば前回weightsを維持して出力しているか
  - 全営業日のweightsが生成されているか

### 3. 修正方針

**重要:**
- 修正は **analysis側のみで完結**（core禁止）
- core側のスクリプト（`run_scoring.py`, `scoring_engine.py`）は触らない

**修正対象:**
- `scripts/analysis/generate_variant_weights.py` - weights生成ロジック
- `scripts/analysis/backtest_from_weights.py` - リターン計算ロジック
- `scripts/analysis/build_cross4_target_weights.py` - 合成ロジック（必要に応じて）

---

## 参照

- `docs/old_analysis_deprecation.md` - 旧analysisの段階的廃棄方針
- `docs/ladder_specification.md` - ladder仕様（ソース・オブ・トゥルース）
- `docs/core_protection_rules.md` - core保護ルール

