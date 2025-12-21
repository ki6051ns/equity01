# cross4 weights版実装状況

## 実施内容サマリ

### 1. ladder仕様の特定（指示A）

**完了:**
- `docs/ladder_specification.md` を作成
- ラダー方式の仕様を根拠行リンクで記録
- **重要発見**: リバランス日判定やoffsetは存在しない。毎日weightsを生成し、過去horizon本の平均を使用する方式

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:101-357`](scripts/analysis/horizon_ensemble.py#L101-L357) - `backtest_with_horizon`関数
- キュー保持: [`scripts/analysis/horizon_ensemble.py:256-258`](scripts/analysis/horizon_ensemble.py#L256-L258)
- 平均計算: [`scripts/analysis/horizon_ensemble.py:278`](scripts/analysis/horizon_ensemble.py#L278)

---

### 2. weights生成への移植（指示B）

**完了:**
- `scripts/analysis/generate_variant_weights.py` をアップグレード
- nonladder: 現状通り（horizonごとにリバランス）
- ladder: 既存ロジックを移植（毎日weights生成、過去horizon本の平均を使用）

**実装内容:**
- 全営業日のweightsを生成（ladder方式では全営業日を含める）
- データがない日でも、キューがあれば前回weightsを維持
- クリーニング（`clean_target_weights`）を適用

**出力:**
- `data/processed/weights/h{H}_{ladder}_{variant}.parquet`
  - 例: `h60_ladder_rank_only.parquet`, `h90_ladder_zdownvol.parquet`

---

### 3. 一致検証のFAIL原因が見える化（指示C）

**完了:**
- `scripts/analysis/verify_cross4_equivalence.py` を拡張
- 差分が大きい日top20をCSVに出力
- その日のweights上位銘柄（cross4/rank_only/zdownvol）もダンプ

**追加出力:**
- `research/reports/cross4_weights_equivalence_top20_diff.csv` - 差分が大きい日top20
- `research/reports/cross4_weights_top_diff_date_{YYYYMMDD}.csv` - 差分最大日のweights上位30銘柄
- `research/reports/cross4_weights_rank_only_top_diff_date_{YYYYMMDD}.csv` - rank_only weights上位30銘柄
- `research/reports/cross4_weights_zdownvol_top_diff_date_{YYYYMMDD}.csv` - zdownvol weights上位30銘柄

---

## 重要な注意点

### backtest_from_weights.pyの前提

**注意:**
- `backtest_from_weights.py` は "date列の並び順" で翌日リターンを取りに行っている
- リバランス日が飛ぶ（ラダーで維持する）ようになると、日付列が「全営業日」になっている前提で安定する

**対応:**
- `generate_variant_weights.py` のladder実装では、**全営業日のweightsを生成**（維持日も含める）
- データがない日でも、キューがあれば前回weightsを維持して出力

---

## 実行方法

### 一括実行（推奨）

すべてのステップ（①→②→③→④）を自動実行します：

```bash
python scripts/analysis/run_cross4_weights_verification.py
```

詳細は `docs/verify_cross4_execution_guide.md` を参照してください。

---

### 個別実行

詳細を確認しながら実行する場合：

weights版cross4の検証は以下の順序で実行してください：

**① variant別/horizon別のweightsを生成**
```bash
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 120 --ladder ladder

python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 5 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 10 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 60 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 90 --ladder ladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 120 --ladder ladder
```

**② cross4 target weightsを生成**
```bash
python scripts/analysis/build_cross4_target_weights.py
# → 出力: data/processed/weights/cross4_target_weights.parquet
```

**③ weights→returnsを計算**
```bash
python scripts/analysis/backtest_from_weights.py
# → 出力: data/processed/weights_bt/cross4_from_weights.parquet
```

**④ 一致検証**
```bash
python scripts/analysis/verify_cross4_equivalence.py
# → 出力: research/reports/cross4_weights_equivalence.csv
# → 出力: research/reports/cross4_weights_equivalence_top20_diff.csv（FAIL時）
# → 出力: research/reports/cross4_weights_top_diff_date_{YYYYMMDD}.csv（FAIL時）
```

---

## 参照

- `docs/ladder_specification.md` - ladder仕様（ソース・オブ・トゥルース）
- `docs/analysis_research_pipeline.md` - analysis研究フロー（weights版cross4の流れ）
- `scripts/analysis/generate_variant_weights.py` - weights生成（ladder対応済み）

