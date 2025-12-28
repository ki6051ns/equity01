"""
非ラダー版（baseline）とラダー版の結果を比較するスクリプト
H=1,5,10,20,60それぞれで比較
"""
import pandas as pd
import numpy as np
from pathlib import Path

horizons = [1, 5, 10, 20, 60, 90, 120]

print("=" * 80)
print("=== 非ラダー版 vs ラダー版 比較 ===")
print("=" * 80)

# 非ラダー版（baseline）を読み込み
baseline_path = Path("data/processed/paper_trade_with_alpha_beta.parquet")
if not baseline_path.exists():
    print(f"エラー: {baseline_path} が見つかりません")
    print("先に paper_trade.py を実行してください")
    exit(1)

df_baseline = pd.read_parquet(baseline_path)
df_baseline = df_baseline.sort_values("trade_date")
print(f"\n非ラダー版（baseline）: {len(df_baseline)} 日分")
print(f"期間: {df_baseline['trade_date'].min()} ～ {df_baseline['trade_date'].max()}")

# 各ホライゾンで比較
comparison_rows = []

for h in horizons:
    print("\n" + "=" * 80)
    print(f"=== H{h} 比較 ===")
    print("=" * 80)
    
    # ラダー版を読み込み
    ladder_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}.parquet")
    if not ladder_path.exists():
        print(f"  [H{h}] ラダー版が見つかりません: {ladder_path}")
        continue
    
    df_ladder = pd.read_parquet(ladder_path)
    df_ladder = df_ladder.sort_values("trade_date")
    print(f"  [H{h}] ラダー版: {len(df_ladder)} 日分")
    print(f"  期間: {df_ladder['trade_date'].min()} ～ {df_ladder['trade_date'].max()}")
    
    # 日付でマージ
    df_merged = df_baseline[["trade_date", "port_ret_cc", "tpx_ret_cc", "rel_alpha_daily"]].merge(
        df_ladder[["trade_date", "port_ret_cc", "tpx_ret_cc", "rel_alpha_daily"]],
        on="trade_date",
        how="inner",
        suffixes=("_baseline", "_ladder")
    )
    
    if len(df_merged) == 0:
        print(f"  [H{h}] 共通日付がありません")
        continue
    
    print(f"  共通日数: {len(df_merged)} 日")
    
    # 累積パフォーマンス
    baseline_total_port = (1 + df_merged["port_ret_cc_baseline"]).prod() - 1
    baseline_total_tpx = (1 + df_merged["tpx_ret_cc_baseline"]).prod() - 1
    baseline_total_alpha = baseline_total_port - baseline_total_tpx
    
    ladder_total_port = (1 + df_merged["port_ret_cc_ladder"]).prod() - 1
    ladder_total_tpx = (1 + df_merged["tpx_ret_cc_ladder"]).prod() - 1
    ladder_total_alpha = ladder_total_port - ladder_total_tpx
    
    print(f"\n【累積パフォーマンス】")
    print(f"  非ラダー版:")
    print(f"    Port: {baseline_total_port:+.4%}")
    print(f"    TOPIX: {baseline_total_tpx:+.4%}")
    print(f"    α: {baseline_total_alpha:+.4%}")
    print(f"  ラダー版:")
    print(f"    Port: {ladder_total_port:+.4%}")
    print(f"    TOPIX: {ladder_total_tpx:+.4%}")
    print(f"    α: {ladder_total_alpha:+.4%}")
    print(f"  差分:")
    print(f"    Port: {(ladder_total_port - baseline_total_port):+.4%}")
    print(f"    α: {(ladder_total_alpha - baseline_total_alpha):+.4%}")
    
    # 相関係数
    corr_port = df_merged["port_ret_cc_baseline"].corr(df_merged["port_ret_cc_ladder"])
    corr_alpha = df_merged["rel_alpha_daily_baseline"].corr(df_merged["rel_alpha_daily_ladder"])
    
    print(f"\n【相関係数】")
    print(f"  port_ret_cc: {corr_port:.4f}")
    print(f"  rel_alpha_daily: {corr_alpha:.4f}")
    
    # 年率統計
    days = len(df_merged)
    years = days / 252.0
    
    # 非ラダー版
    baseline_annual_return = (1 + baseline_total_port) ** (1.0 / years) - 1 if years > 0 else 0.0
    baseline_annual_vol = df_merged["port_ret_cc_baseline"].std() * np.sqrt(252)
    baseline_sharpe = baseline_annual_return / baseline_annual_vol if baseline_annual_vol > 0 else float("nan")
    baseline_alpha_annual = (1 + baseline_total_alpha) ** (1.0 / years) - 1 if years > 0 else 0.0
    baseline_alpha_vol = df_merged["rel_alpha_daily_baseline"].std() * np.sqrt(252)
    baseline_alpha_sharpe = baseline_alpha_annual / baseline_alpha_vol if baseline_alpha_vol > 0 else float("nan")
    
    # ラダー版
    ladder_annual_return = (1 + ladder_total_port) ** (1.0 / years) - 1 if years > 0 else 0.0
    ladder_annual_vol = df_merged["port_ret_cc_ladder"].std() * np.sqrt(252)
    ladder_sharpe = ladder_annual_return / ladder_annual_vol if ladder_annual_vol > 0 else float("nan")
    ladder_alpha_annual = (1 + ladder_total_alpha) ** (1.0 / years) - 1 if years > 0 else 0.0
    ladder_alpha_vol = df_merged["rel_alpha_daily_ladder"].std() * np.sqrt(252)
    ladder_alpha_sharpe = ladder_alpha_annual / ladder_alpha_vol if ladder_alpha_vol > 0 else float("nan")
    
    print(f"\n【年率統計】")
    print(f"  非ラダー版:")
    print(f"    年率リターン: {baseline_annual_return:+.4%}")
    print(f"    年率ボラ: {baseline_annual_vol:+.4%}")
    print(f"    年率Sharpe: {baseline_sharpe:+.4f}")
    print(f"    年率αリターン: {baseline_alpha_annual:+.4%}")
    print(f"    年率αボラ: {baseline_alpha_vol:+.4%}")
    print(f"    年率αSharpe: {baseline_alpha_sharpe:+.4f}")
    print(f"  ラダー版:")
    print(f"    年率リターン: {ladder_annual_return:+.4%}")
    print(f"    年率ボラ: {ladder_annual_vol:+.4%}")
    print(f"    年率Sharpe: {ladder_sharpe:+.4f}")
    print(f"    年率αリターン: {ladder_alpha_annual:+.4%}")
    print(f"    年率αボラ: {ladder_alpha_vol:+.4%}")
    print(f"    年率αSharpe: {ladder_alpha_sharpe:+.4f}")
    
    # ドローダウン
    baseline_cum = (1.0 + df_merged["port_ret_cc_baseline"]).cumprod()
    baseline_dd = (baseline_cum / baseline_cum.cummax() - 1.0).min()
    
    ladder_cum = (1.0 + df_merged["port_ret_cc_ladder"]).cumprod()
    ladder_dd = (ladder_cum / ladder_cum.cummax() - 1.0).min()
    
    print(f"\n【最大ドローダウン】")
    print(f"  非ラダー版: {baseline_dd:+.4%}")
    print(f"  ラダー版: {ladder_dd:+.4%}")
    
    # 比較結果を保存
    comparison_rows.append({
        "horizon": h,
        "baseline_total_port": baseline_total_port,
        "baseline_total_alpha": baseline_total_alpha,
        "baseline_annual_return": baseline_annual_return,
        "baseline_annual_vol": baseline_annual_vol,
        "baseline_sharpe": baseline_sharpe,
        "baseline_alpha_sharpe": baseline_alpha_sharpe,
        "baseline_max_dd": baseline_dd,
        "ladder_total_port": ladder_total_port,
        "ladder_total_alpha": ladder_total_alpha,
        "ladder_annual_return": ladder_annual_return,
        "ladder_annual_vol": ladder_annual_vol,
        "ladder_sharpe": ladder_sharpe,
        "ladder_alpha_sharpe": ladder_alpha_sharpe,
        "ladder_max_dd": ladder_dd,
        "corr_port": corr_port,
        "corr_alpha": corr_alpha,
        "diff_total_port": ladder_total_port - baseline_total_port,
        "diff_total_alpha": ladder_total_alpha - baseline_total_alpha,
        "diff_sharpe": ladder_sharpe - baseline_sharpe,
        "diff_alpha_sharpe": ladder_alpha_sharpe - baseline_alpha_sharpe,
    })

# 比較サマリテーブル
if comparison_rows:
    df_comparison = pd.DataFrame(comparison_rows)
    
    print("\n" + "=" * 80)
    print("=== 比較サマリテーブル ===")
    print("=" * 80)
    
    # 累積リターン比較
    print("\n【累積リターン比較】")
    display_cols = ["horizon", "baseline_total_port", "ladder_total_port", "diff_total_port",
                   "baseline_total_alpha", "ladder_total_alpha", "diff_total_alpha"]
    display_df = df_comparison[display_cols].copy()
    for col in display_cols[1:]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    print(display_df.to_string(index=False))
    
    # 年率Sharpe比較
    print("\n【年率Sharpe比較】")
    display_cols = ["horizon", "baseline_sharpe", "ladder_sharpe", "diff_sharpe",
                   "baseline_alpha_sharpe", "ladder_alpha_sharpe", "diff_alpha_sharpe"]
    display_df = df_comparison[display_cols].copy()
    for col in display_cols[1:]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:+.4f}")
    print(display_df.to_string(index=False))
    
    # 相関係数
    print("\n【相関係数】")
    display_cols = ["horizon", "corr_port", "corr_alpha"]
    display_df = df_comparison[display_cols].copy()
    for col in display_cols[1:]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.4f}")
    print(display_df.to_string(index=False))
    
    # 保存
    out_path = Path("data/processed/ladder_vs_baseline_comparison.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_comparison.to_parquet(out_path, index=False)
    print(f"\n✓ 比較結果を保存: {out_path}")

print("\n" + "=" * 80)
print("=== 比較完了 ===")
print("=" * 80)

