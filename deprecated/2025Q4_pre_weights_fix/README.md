# deprecated/2025Q4_pre_weights_fix/

## 概要

2025年Q4（weights型修正前）の旧パイプライン・検証スクリプトを集約。

## 移動理由

1. **旧パイプライン由来**（旧 `port_ret_cc` 定義に依存）
2. **eval / backtest が *weights再構築（w[t-1]r[t]）と不整合**
3. **本番（prd）要件に含まれない分析・検証スクリプト**

## 移動基準

- weights型ファイル（`.parquet`）は**残す**（`data/processed/weights/`配下）
- weights生成スクリプトは**残す**（`scripts/analysis/generate_variant_weights.py`, `build_cross4_target_weights*.py`, `backtest_from_weights*.py`）
- **検証・分析・デバッグスクリプト**を移動

## 移動対象

### 1. eval vs weights比較・検証スクリプト
- `debug_eval_vs_weights_day.py`
- `compare_eval_vs_weights_stop.py`

### 2. デバッグスクリプト
- `debug_single_date_reproduction.py`
- `debug_diff_day_attribution.py`
- `debug_eval_return_transformation.py`

### 3. 旧パイプライン由来（port_ret_cc使用）
- `eval_stop_regimes.py`
- `eval_stop_regimes_robustness.py`
- `rebuild_port_ret_from_weights.py`

### 4. 検証スクリプト
- `verify_port_ret_cc_raw.py`
- `audit_diff_days_symbol_returns.py`
- `verify_cross4_equivalence.py`
- `verify_stop_weights_integrity.py`
- `check_stop_weights_inverse.py`
- `verify_stop_cross4_equivalence.py`

### 5. 比較・分析スクリプト
- `compare_cross4_returns.py`
- `analyze_cross4_cumret_diff_monthly.py`

### 6. 検証実行スクリプト
- `run_all_stop_comparison.py`
- `run_all_stop_comparison_utf8.bat`
- `run_cross4_weights_verification.py`

### 7. ensemble系スクリプト（12ファイル）
- `ensemble_custom_weights.py`
- `ensemble_rank_only.py`
- `ensemble_variant_cross.py`
- `ensemble_variant_cross2.py`
- `ensemble_variant_cross3.py`
- `ensemble_variant_cross4.py`
- `ensemble_zclip.py`
- `ensemble_zdownbeta.py`
- `ensemble_zdowncombo.py`
- `ensemble_zdownvol.py`
- `ensemble_zlin.py`
- `ensemble_zlowvol.py`

### 8. run_all系スクリプト（7ファイル）
- `run_all_rank_only.py`
- `run_all_zclip.py`
- `run_all_zdownbeta.py`
- `run_all_zdowncombo.py`
- `run_all_zdownvol.py`
- `run_all_zlin.py`
- `run_all_zlowvol.py`

### 9. その他の分析・可視化スクリプト
- `aggregate_yearly_performance.py`（analyze系）
- `backtest_non_ladder.py`
- `build_bpi.py`
- `calc_bpi_126d.py`
- `check_h1_stats.py`（check系）
- `check_horizon_progress.py`（check系）
- `compare_ladder_vs_baseline.py`（compare系）
- `dynamic_portfolio_performance.py`
- `example_dynamic_allocation.py`
- `horizon_ensemble.py`
- `monthly_performance.py`（performance分析系）
- `rolling_relative_alpha.py`
- `run_eval_report.py`（eval系）
- `run_ensemble_custom_simple.py`
- `run_ensemble_from_existing.py`
- `run_single_horizon.py`
- `scoring_variants.py`（variant探索用）
- `visualize_bpi.py`（visualize系）
- `visualize_bpi_126d.py`（visualize系）
- `visualize_inverse_etf_126d.py`（visualize系）
- `visualize_regime_hmm.py`（visualize系）

## 削除タイミング

- stgで 2〜3回連続で未参照・未使用を確認
- prdブランチ作成後に完全削除

## 参照切替済み

以下のファイルから参照を削除または修正済み:
- `scripts/analysis/build_cross4_target_weights_with_stop.py`: `rebuild_port_ret_from_weights`への参照を削除
- `scripts/analysis/build_cross4_target_weights.py`: `ensemble_variant_cross4`への参照を削除（直接定義に変更）
- `README.md`: 検証フローセクションを非推奨に更新
- `scripts/core/run_equity01_eval.py`: `run_eval_report.py`への参照をdeprecatedパスに更新

## stg整理（2025-12-28）

stgでは「weights型（core）」だけを残し、以下をdeprecatedに移動:

### 残すcore 5ファイル（scripts/analysis/）
- `generate_variant_weights.py`
- `build_cross4_target_weights.py`
- `build_cross4_target_weights_with_stop.py`
- `backtest_from_weights.py`
- `backtest_from_weights_with_stop.py`

### scripts/core/から移動したeval型・未完成ファイル

以下のファイルは`scripts/core/`にありましたが、eval型（評価・分析用）または未完成のためdeprecatedに移動:

- `scripts/core/run_equity01_eval.py` - 統合評価スクリプト（port_ret_cc使用）
- `scripts/core/calc_alpha_beta.py` - ペーパートレード結果に相対αを後乗せ（port_ret_cc使用）
- `scripts/core/build_dynamic_portfolio.py` - 動的ウェイトポートフォリオ構築（ensemble系に依存、port_ret_cc使用）
- `scripts/core/build_regime_hmm.py` - HMMレジームクラスタリング（horizon_ensemble_variant_cross4.parquetに依存、port_ret_cc使用、モニタリング用途のみ）
- `scripts/core/event_guard.py` - イベントガード（ロジック構築未完成、build_portfolio.pyとgenerate_variant_weights.pyから削除）

**残すcoreファイル（scripts/core/）:**
- `universe_builder.py` - ユニバース構築（実運営に必要）
- `download_prices.py` - 価格データ取得（実運営に必要）
- `build_features.py` - 特徴量構築（実運営に必要）
- `run_scoring.py` - スコアリング実行（実運営に必要）
- `scoring_engine.py` - スコアリングエンジン（実運営に必要）
- `build_portfolio.py` - ポートフォリオ構築（運用終点生成、実運営に必要）

### Runの一本化

- `scripts/stg_sanity_check.py` を新規作成
- stgの最低限整合性チェック（import + 軽い存在チェック）のみ実施
- 重いbacktestは回さない（実行時間を短く）

