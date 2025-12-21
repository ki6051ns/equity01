# cross4 / STOP の扱い（analysis固定）

## 概要

cross4 / STOP 系は **analysis側（検証・評価）** の系統として明確化し、coreフロー（運用終点）とは **混線させない** ことを確認します。

---

## 位置づけ

### cross4

**生成:**
- `scripts/analysis/ensemble_variant_cross4.py` で生成
- **出力**: `data/processed/horizon_ensemble_variant_cross4.parquet`

**使用:**
- `scripts/analysis/eval_stop_regimes.py` で使用
- `scripts/analysis/eval_stop_regimes_robustness.py` で使用
- `scripts/core/build_regime_hmm.py:58` で使用（KEEP_STG_ANALYSIS、coreフローとは別系統）

**分類:**
- **KEEP_STG_ANALYSIS** - stgレビュー・採用判断に必要（検証/評価レポート）

### STOP

**評価・検証:**
- `scripts/analysis/eval_stop_regimes.py` で評価・検証
- `scripts/analysis/eval_stop_regimes_robustness.py` でロバストネステスト

**レジームHMM構築:**
- `scripts/core/build_regime_hmm.py:345` でレジームHMM構築
  - **入力**: `horizon_ensemble_variant_cross4.parquet` ([`build_regime_hmm.py:58`](scripts/core/build_regime_hmm.py#L58))
  - **出力**: `data/processed/regime_labels.parquet` ([`build_regime_hmm.py:345`](scripts/core/build_regime_hmm.py#L345))

**分類:**
- **KEEP_STG_ANALYSIS** - stgレビュー・採用判断に必要（検証/評価レポート）

**注意:**
- `scripts/core/build_regime_hmm.py` は `scripts/core/` に配置されているが、cross4を使用しているため **KEEP_STG_ANALYSIS** として扱う
- coreフロー（運用終点）とは別系統（analysis側）
- 将来的に `scripts/analysis/` に移動することも検討可能

---

## coreフローとの関係

### coreフロー（運用終点）

**終点:**
- `data/processed/daily_portfolio_guarded.parquet` - ポートフォリオ構築の最終出力
- 生成元: `scripts/core/build_portfolio.py:63`

**独立性:**
- cross4 / STOP とは独立して生成される
- coreフローは cross4 / STOP を使用しない

### cross4 / STOP（analysis側）

**用途:**
- 検証・評価・モニタリング用途
- stgレビュー・採用判断に必要

**依存関係:**
- analysis側がcore生成物（parquet）を読み込む（読み取り専用）
- core生成物に書き戻さない

---

## 混線の確認

### core→analysis依存ゼロの確認

**確認コマンド:**
```bash
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
```

**結果:**
- **0件** - coreからanalysisへの依存は存在しない ✅

**結論:**
- coreフローは cross4 / STOP を使用しない
- core→analysis依存ゼロが保証されている

### build_regime_hmm.py の位置づけ

**現状:**
- `scripts/core/build_regime_hmm.py` に配置されている
- cross4を使用しているため、実質的にはanalysis用途

**分類:**
- **KEEP_STG_ANALYSIS** - stgレビュー・採用判断に必要
- coreフロー（運用終点）とは別系統

**推奨対応:**
- 現状のまま `scripts/core/` に配置しても問題ない（分類はKEEP_STG_ANALYSIS）
- 将来的に `scripts/analysis/` に移動することも検討可能（ただし、importパスの修正が必要）

---

## 参照

- `docs/classification_rules.md` - ファイル分類ルール
- `docs/pipeline_graph.md` - パイプライン依存図
- `docs/core_flow_table.md` - coreフロー表

