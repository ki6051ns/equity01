# 旧analysis（returns合成）の段階的廃棄方針

## 概要

cross4を「Return合成」から「Weight合成」に移行し、weights→returnsが既存return合成cross4と一致することを証明した後、旧analysisスクリプトを段階的に廃棄します。

---

## 旧analysisスクリプト（returns合成方式）

以下のスクリプトは「returns合成（旧方式）」として扱い、weights版cross4がPASSしたら段階的に不要化します：

### 対象スクリプト

1. **`scripts/analysis/run_all_rank_only.py`**
   - rank-only variantのバックテストを実行
   - 出力: `data/processed/paper_trade_h*_*_rank.parquet`（returns系列）

2. **`scripts/analysis/run_all_zdownvol.py`**
   - z_downvol (Variant E) のバックテストを実行
   - 出力: `data/processed/paper_trade_h*_*_zdownvol.parquet`（returns系列）

3. **`scripts/analysis/ensemble_rank_only.py`**
   - rank-only variantのhorizon合成（returns合成）
   - 出力: `data/processed/horizon_ensemble_rank_only.parquet`

4. **`scripts/analysis/ensemble_variant_cross4.py`**
   - cross4アンサンブル（variant合成＋horizon合成、returns合成）
   - 出力: `data/processed/horizon_ensemble_variant_cross4.parquet`

### 役割

**旧方式の位置づけ:**
- 研究用：バックテスト/アンサンブル成績生成
- **執行用のtarget weightは生成しない**
- returns系列を直接合成する方式

**重要:**
- これらはcoreに依存して良い（core生成物を読み込む）
- **coreへ書き戻し（生成物をcoreが読む）は禁止**
- analysis側で完結

---

## weights版cross4（新方式）

### 新方式のスクリプト

1. **`scripts/analysis/generate_variant_weights.py`**
   - variant別/horizon別の日次weightsを生成
   - 出力: `data/processed/weights/h{H}_{ladder}_{variant}.parquet`

2. **`scripts/analysis/build_cross4_target_weights.py`**
   - weights合成（variant合成＋horizon合成）
   - 出力: `data/processed/weights/cross4_target_weights.parquet`

3. **`scripts/analysis/backtest_from_weights.py`**
   - weights→returnsでポートフォリオリターンを計算
   - 出力: `data/processed/weights_bt/cross4_from_weights.parquet`

4. **`scripts/analysis/verify_cross4_equivalence.py`**
   - 旧方式と新方式の一致検証
   - 出力: `research/reports/cross4_weights_equivalence.csv`

### 新方式の利点

- **weights起点**でcross4を構築できる（執行用target weightの生成が可能）
- 既存return合成cross4と一致することが証明される
- より明確な実行順序と依存関係

---

## 廃棄スケジュール

### Phase 1: 一致検証（現在）

- [ ] `verify_cross4_equivalence.py` が PASS
- [ ] 旧方式と新方式のリターンが一致することを確認

### Phase 2: 参照先の移行（PASS後）

- [ ] `eval_stop_regimes.py` などのSTOP検証スクリプトが新方式を参照するように移行
- [ ] 旧方式の参照を新方式に置き換え

### Phase 3: 旧スクリプトのアーカイブ（参照移行完了後）

- [ ] `scripts/analysis/run_all_rank_only.py` → `archive/analysis_deprecated/`
- [ ] `scripts/analysis/run_all_zdownvol.py` → `archive/analysis_deprecated/`
- [ ] `scripts/analysis/ensemble_rank_only.py` → `archive/analysis_deprecated/`
- [ ] `scripts/analysis/ensemble_variant_cross4.py` → `archive/analysis_deprecated/`
- [ ] 各ファイルに `DEPRECATED` コメントを追加

**注意:**
- 即座に削除しない（段階的に移行）
- アーカイブ後も参照できるようにする

---

## 参照

- `docs/analysis_research_pipeline.md` - analysis研究フロー（weights版cross4の流れ）
- `docs/cross4_weights_implementation_status.md` - weights版cross4の実装状況
- `docs/ladder_specification.md` - ladder仕様（ソース・オブ・トゥルース）

