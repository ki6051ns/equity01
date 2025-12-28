"""
既存の結果ファイルを使ってアンサンブルと統計情報を計算するスクリプト
"""
import sys
from pathlib import Path

# horizon_ensembleの関数をインポート
sys.path.insert(0, str(Path(__file__).parent))
from horizon_ensemble import (
    calc_alpha_beta_for_horizon,
    summarize_horizon,
    compute_monthly_perf,
    print_horizon_performance,
    ensemble_horizons,
    print_h1_statistics,
)

import pandas as pd

horizons = [1, 5, 10, 20, 60]

print("=" * 60)
print("=== Horizon Ensemble (既存ファイルから) ===")
print("=" * 60)

# 各ホライゾンの結果を読み込み
summary_rows = []
horizon_alpha_dfs = {}

for h in horizons:
    print(f"\n[STEP {h}] H{h} の結果を読み込み中...")
    
    # 既存ファイルを確認
    pt_path = Path(f"data/processed/paper_trade_h{h}.parquet")
    if not pt_path.exists():
        print(f"  [H{h}] 警告: {pt_path} が見つかりません。スキップします。")
        continue
    
    # 相対αを計算
    df_pt = pd.read_parquet(pt_path)
    print(f"  [H{h}] バックテスト結果: {len(df_pt)} 日分")
    
    df_alpha = calc_alpha_beta_for_horizon(df_pt, h)
    print(f"  [H{h}] 相対α計算完了")
    
    # H1の場合は統計情報を表示
    if h == 1:
        print_h1_statistics(df_alpha)
    
    # ホライゾン別サマリを計算
    summary = summarize_horizon(df_alpha, h)
    summary_rows.append(summary)
    horizon_alpha_dfs[h] = df_alpha
    
    print(
        f"  [H{h}] total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"max_dd={summary['max_drawdown']:.2%}"
    )
    
    # 月次・年次パフォーマンスを計算
    print(f"  [H{h}] 月次・年次集計中...")
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=f"H{h}",
        out_prefix="data/processed/horizon"
    )
    print(f"  [H{h}] 月次・年次集計完了")
    
    # ホライゾン別パフォーマンス表示
    print_horizon_performance(df_alpha, h, monthly, yearly)

# ホライゾン別サマリを保存・表示
if summary_rows:
    df_summary = pd.DataFrame(summary_rows)
    summary_path = Path("data/processed/horizon_perf_summary.parquet")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    df_summary.to_parquet(summary_path, index=False)
    
    print("\n=== ホライゾン別パフォーマンスサマリ ===")
    display_cols = ["horizon", "days", "total_port", "total_tpx", "total_alpha", 
                   "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    print(display_df.to_string(index=False))
    print(f"\n✓ サマリ保存先: {summary_path}")

# アンサンブル
print("\n[STEP] ホライゾンアンサンブル実行中...")
df_ens = ensemble_horizons(horizons)
print(f"  アンサンブル完了: {len(df_ens)} 日分")

# アンサンブル版の相対αを計算
df_ens_alpha = df_ens[["trade_date", "port_ret_cc_ens", "rel_alpha_ens", "tpx_ret_cc", "cum_port_ens", "cum_tpx"]].copy()
df_ens_alpha = df_ens_alpha.rename(columns={
    "port_ret_cc_ens": "port_ret_cc",
    "rel_alpha_ens": "rel_alpha_daily",
    "cum_port_ens": "cum_port"
})

# アンサンブル版の月次・年次集計
print("  アンサンブル版の月次・年次集計中...")
ensemble_monthly, ensemble_yearly = compute_monthly_perf(
    df_ens_alpha,
    label="ensemble",
    out_prefix="data/processed/horizon"
)

# アンサンブル版のパフォーマンス表示
horizon_str = ",".join([f"H{h}" for h in horizons])
print(f"\n=== Ensemble ({horizon_str}) Performance ===")
print_horizon_performance(df_ens_alpha, 0, ensemble_monthly, ensemble_yearly)

# アンサンブル版の年率シャープレシオ（総合）を計算
import numpy as np
ret = df_ens_alpha["port_ret_cc"]
mu_daily = ret.mean()
sigma_daily = ret.std()
sharpe_annual = (mu_daily * 252) / (sigma_daily * np.sqrt(252)) if sigma_daily > 0 else float("nan")
print(f"\nEnsemble annual Sharpe (total): {sharpe_annual:.4f}")

print(f"\n✓ 保存先: data/processed/horizon_ensemble.parquet")
print("=" * 60)
print("=== Horizon Ensemble Done ===")
print("=" * 60)

