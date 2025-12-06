"""
単一ホライゾンのバックテストを実行するスクリプト
"""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("使用方法: python scripts/run_single_horizon.py <horizon>")
    print("例: python scripts/run_single_horizon.py 5")
    sys.exit(1)

horizon = int(sys.argv[1])

# horizon_ensembleの関数をインポート
sys.path.insert(0, str(Path(__file__).parent))
from horizon_ensemble import (
    build_features_shared,
    backtest_with_horizon,
    calc_alpha_beta_for_horizon,
    summarize_horizon,
    compute_monthly_perf,
    print_horizon_performance,
    print_h1_statistics,
)

print("=" * 60)
print(f"=== H{horizon} バックテスト実行 ===")
print("=" * 60)

# 共有featureと価格データを読み込み
print("\n[STEP 1] 共有featureと価格データを読み込み中...")
features, prices = build_features_shared()
print(f"  Features: {len(features)} rows")
print(f"  Prices: {len(prices)} rows")

# バックテスト実行
print(f"\n[STEP 2] H{horizon} バックテスト実行中...")
df_pt = backtest_with_horizon(features, prices, horizon)
pt_path = Path(f"data/processed/paper_trade_h{horizon}.parquet")
pt_path.parent.mkdir(parents=True, exist_ok=True)
df_pt.to_parquet(pt_path, index=False)
print(f"  [H{horizon}] バックテスト完了: {len(df_pt)} 日分")

# 相対α計算
print(f"  [H{horizon}] 相対α計算中...")
df_alpha = calc_alpha_beta_for_horizon(df_pt, horizon)
print(f"  [H{horizon}] 相対α計算完了")

# H1の場合は統計情報を表示
if horizon == 1:
    print_h1_statistics(df_alpha)

# サマリ計算
print(f"  [H{horizon}] サマリ計算中...")
summary = summarize_horizon(df_alpha, horizon)
print(
    f"  [H{horizon}] total_port={summary['total_port']:.2%}, "
    f"total_alpha={summary['total_alpha']:.2%}, "
    f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
    f"max_dd={summary['max_drawdown']:.2%}"
)

# 月次・年次パフォーマンスを計算
print(f"  [H{horizon}] 月次・年次集計中...")
monthly, yearly = compute_monthly_perf(
    df_alpha,
    label=f"H{horizon}",
    out_prefix="data/processed/horizon"
)
print(f"  [H{horizon}] 月次・年次集計完了")

# パフォーマンス表示
print_horizon_performance(df_alpha, horizon, monthly, yearly)

print("\n" + "=" * 60)
print(f"=== H{horizon} バックテスト完了 ===")
print("=" * 60)

