# cross4 weights版実装サマリ

## 概要

cross4を「Return合成」から「Weight合成」に昇格し、weights→returns が現行cross4(returns合成)＋STOPと一致することを回帰テストで証明する実装です。

---

## 実装ファイル

### 1. scripts/analysis/build_cross4_target_weights.py

**役割**: cross4 target weightsを生成する（analysis内で完結、coreへ書き戻し禁止）

**入力**:
- `data/processed/weights/h{H}_{ladder}_{variant}.parquet`（variant別/horizon別weights）

**出力**:
- `data/processed/weights/cross4_target_weights.parquet`（全期間）
- `data/processed/weights/cross4_target_weights_latest.parquet`（最新日のみ）

**合成ロジック**:
- Variant合成: `w_cross4_h = 0.75 * w_rank_only_h + 0.25 * w_zdownvol_h`
- Horizon合成: `w_cross4 = Σ_h (horizon_weight[h] * w_cross4_h)`
- 正規化: `sum(w_cross4)=1`（ロングオンリー前提）

### 2. scripts/analysis/backtest_from_weights.py

**役割**: weightsからreturnsを計算するバックテスト

**入力**:
- `data/processed/weights/cross4_target_weights.parquet`（date, symbol, weight）
- 価格データ（data_loaderから読み込む）

**出力**:
- `data/processed/weights_bt/cross4_from_weights.parquet`（trade_date, port_ret_cc, cumulative, rel_alpha_daily）

### 3. scripts/analysis/verify_cross4_equivalence.py

**役割**: weights→returnsで得たcross4リターンが、既存horizon_ensemble_variant_cross4.parquet（return合成）と一致することを検証

**比較対象**:
- A: 既存 `horizon_ensemble_variant_cross4.parquet`（return合成）
- B: 新 `cross4_from_weights.parquet`（weights→returns）

**出力**:
- `research/reports/cross4_weights_equivalence.csv`
  - `mean_abs_diff_daily`, `max_abs_diff_daily`, `cumret_diff_last`
  - 許容誤差: `1e-8`
  - 判定: `PASS/FAIL`

### 4. scripts/analysis/generate_variant_weights.py

**役割**: variant別/horizon別の日次weightsを生成する（ヘルパー）

**入力**:
- `data/processed/daily_feature_scores.parquet`（core生成物）

**出力**:
- `data/processed/weights/h{H}_{ladder}_{variant}.parquet`（date, symbol, weight）

**使用方法**:
```bash
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 1 --ladder nonladder
```

---

## 実行フロー

### ステップ1: variant別/horizon別のweightsを生成

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

### ステップ2: cross4 target weightsを生成

```bash
python scripts/analysis/build_cross4_target_weights.py
```

### ステップ3: weights→returnsを計算

```bash
python scripts/analysis/backtest_from_weights.py
```

### ステップ4: 一致検証

```bash
python scripts/analysis/verify_cross4_equivalence.py
```

---

## 重要な原則

### coreへ書き戻し禁止

- analysis内で完結（coreへ書き戻し禁止の原則は維持）
- coreは触らない
- まずanalysis内で一致検証

### 運用終点の保護

- core運用終点（`data/processed/daily_portfolio_guarded.parquet`）は維持
- weights版cross4は研究用（prdに接続しない）

### STOPの扱い

- STOPは"執行停止フラグ"として扱う（weights自体は生成して良い）
- STOP日の扱いは「全キャッシュ（w=0）」or「前日維持」or「core同様に執行停止で当日何もしない」

---

## 次のステップ

### PASSした場合

1. 旧analysisの整理（いきなり削除しない）
   - `ensemble_variant_cross4.py` 等の "return合成cross4" を `archive/analysis_deprecated/` に移動
   - READMEとdocsで DEPRECATED 明記
   - 新しい入口は `build_cross4_target_weights.py`（weights版）に統一

2. coreには一切影響を与えない（coreは `daily_portfolio_guarded` のまま）

### FAILした場合

- 詳細差分を確認（`research/reports/cross4_weights_equivalence_detail.parquet`）
- weights生成ロジックと合成ロジックを見直し

---

## 参照

- `docs/analysis_research_pipeline.md` - analysis研究フロー（weights版cross4の流れを追記）
- `docs/core_pipeline_complete.md` - core完結の生成パイプライン
- `docs/cross4_stop_prd_requirements.md` - cross4/STOPのprd最小要件

