# scripts/ 分類計画（JP-stg整理用）

## core/（MVP最小構成 - 実行に必要な主要パイプライン）

### データ取得・前処理
- download_prices.py
- universe_builder.py

### 特徴量・スコアリング
- build_features.py
- run_scoring.py
- scoring_engine.py

### ポートフォリオ構築
- build_portfolio.py
- build_dynamic_portfolio.py

### ガード・リスク管理
- event_guard.py
- build_regime_hmm.py

### 評価・分析
- calc_alpha_beta.py
- run_equity01_eval.py

## analysis/（研究・検証・可視化用 - stgで隔離、prdには持ち込まない）

### 一括実行・アンサンブル実験
- run_all_rank_only.py
- run_all_zclip.py
- run_all_zdownbeta.py
- run_all_zdowncombo.py
- run_all_zdownvol.py
- run_all_zlin.py
- run_all_zlowvol.py
- run_ensemble_custom_simple.py
- run_ensemble_from_existing.py
- run_single_horizon.py
- ensemble_rank_only.py
- ensemble_zclip.py
- ensemble_zdownbeta.py
- ensemble_zdowncombo.py
- ensemble_zdownvol.py
- ensemble_zlin.py
- ensemble_zlowvol.py
- ensemble_custom_weights.py
- ensemble_variant_cross.py
- ensemble_variant_cross2.py
- ensemble_variant_cross3.py
- ensemble_variant_cross4.py
- horizon_ensemble.py

### 検証・評価
- eval_stop_regimes.py
- eval_stop_regimes_robustness.py
- compare_ladder_vs_baseline.py
- backtest_non_ladder.py

### 可視化
- visualize_bpi.py
- visualize_bpi_126d.py
- visualize_inverse_etf_126d.py
- visualize_regime_hmm.py

### 分析・集計
- aggregate_yearly_performance.py
- monthly_performance.py
- rolling_relative_alpha.py
- calc_bpi_126d.py
- build_bpi.py
- dynamic_portfolio_performance.py
- example_dynamic_allocation.py

### チェック・デバッグ
- check_h1_stats.py
- check_horizon_progress.py

## tools/（補助・ユーティリティ）

### データ操作
- data_loader.py
- fetch_prices.py
- build_index_tpx_daily.py

### プレビュー・検証
- preview_parquet.py
- preview_universe.py
- validate_listings.py

### その他補助
- paper_trade.py（評価用バックテスト）
- order_builder.py
- execution_simulator.py
- portfolio_optimizer.py
- post_loss_analyzer.py
- regime_engine.py
- feature_builder.py
- weights_cleaning.py
- calc_minimum_capital.py

