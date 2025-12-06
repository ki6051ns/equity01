"""
カスタムウェイトでアンサンブルを実行するスクリプト

H1: 0.10（非ラダー）
H5: 0.10（非ラダー）
H10: 0.20（非ラダー）
H60: 0.20（ラダー）
H90: 0.20（ラダー）
H120: 0.20（ラダー）
"""
import sys
from pathlib import Path
from typing import Dict

import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加（重複を避ける）

# 相対インポートを修正
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from horizon_ensemble import (
    build_features_shared,
    backtest_with_horizon,
    calc_alpha_beta_for_horizon,
    summarize_horizon,
    compute_monthly_perf,
    print_horizon_performance,
)
from backtest_non_ladder import backtest_non_ladder

# アンサンブル設定
ENSEMBLE_CONFIG = {
    1: {"weight": 0.10, "ladder": False},
    5: {"weight": 0.10, "ladder": False},
    10: {"weight": 0.20, "ladder": False},
    60: {"weight": 0.20, "ladder": True},
    90: {"weight": 0.20, "ladder": True},
    120: {"weight": 0.20, "ladder": True},
}

# ウェイトの合計が1.0か確認
total_weight = sum(cfg["weight"] for cfg in ENSEMBLE_CONFIG.values())
if abs(total_weight - 1.0) > 1e-6:
    print(f"警告: ウェイトの合計が1.0ではありません: {total_weight}")
    print("正規化します...")
    for h in ENSEMBLE_CONFIG:
        ENSEMBLE_CONFIG[h]["weight"] /= total_weight

print("=" * 80)
print("=== カスタムウェイトアンサンブル ===")
print("=" * 80)
print("\nアンサンブル設定:")
for h in sorted(ENSEMBLE_CONFIG.keys()):
    cfg = ENSEMBLE_CONFIG[h]
    mode = "ラダー" if cfg["ladder"] else "非ラダー"
    print(f"  H{h}: {cfg['weight']:.2%} ({mode})")
print(f"合計: {sum(cfg['weight'] for cfg in ENSEMBLE_CONFIG.values()):.2%}")

# 共有featureと価格データを読み込み
print("\n[STEP 1] 共有featureと価格データを読み込み中...")
features, prices = build_features_shared()
print(f"  Features: {len(features)} rows")
print(f"  Prices: {len(prices)} rows")

# 各ホライゾンのバックテストを実行
horizon_results = {}
summary_rows = []

for h, cfg in sorted(ENSEMBLE_CONFIG.items()):
    weight = cfg["weight"]
    is_ladder = cfg["ladder"]
    
    print(f"\n[STEP 2-{h}] H{h} バックテスト実行中... ({'ラダー' if is_ladder else '非ラダー'})")
    
    # 既存ファイルを確認
    if is_ladder:
        pt_path = Path(f"data/processed/paper_trade_h{h}.parquet")
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}.parquet")
    else:
        pt_path = Path(f"data/processed/paper_trade_nonladder_h{h}.parquet")
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_nonladder_h{h}.parquet")
    
    # 既存ファイルがあれば読み込む、なければ実行
    if alpha_path.exists():
        print(f"  [H{h}] 既存ファイルを読み込み中...")
        df_alpha = pd.read_parquet(alpha_path)
        print(f"  [H{h}] 既存ファイル読み込み完了: {len(df_alpha)} 日分")
    else:
        print(f"  [H{h}] バックテスト実行中...")
        if is_ladder:
            df_pt = backtest_with_horizon(features, prices, h)
        else:
            df_pt = backtest_non_ladder(features, prices, h)
        
        pt_path.parent.mkdir(parents=True, exist_ok=True)
        df_pt.to_parquet(pt_path, index=False)
        print(f"  [H{h}] バックテスト完了: {len(df_pt)} 日分")
        
        # 相対α計算
        print(f"  [H{h}] 相対α計算中...")
        df_alpha = calc_alpha_beta_for_horizon(df_pt, h)
        alpha_path.parent.mkdir(parents=True, exist_ok=True)
        df_alpha.to_parquet(alpha_path, index=False)
        print(f"  [H{h}] 相対α計算完了")
    
    # サマリ計算
    summary = summarize_horizon(df_alpha, h)
    summary_rows.append({
        **summary,
        "weight": weight,
        "ladder": is_ladder,
    })
    
    print(
        f"  [H{h}] total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"max_dd={summary['max_drawdown']:.2%}, "
        f"weight={weight:.2%}"
    )
    
    horizon_results[h] = df_alpha

# アンサンブル計算
print("\n[STEP 3] カスタムウェイトアンサンブル実行中...")

# 日付でマージ
dfs_to_merge = []
for h, df_alpha in horizon_results.items():
    weight = ENSEMBLE_CONFIG[h]["weight"]
    df = df_alpha[["trade_date", "port_ret_cc", "rel_alpha_daily"]].copy()
    df = df.rename(columns={
        "port_ret_cc": f"port_ret_cc_h{h}",
        "rel_alpha_daily": f"rel_alpha_h{h}",
    })
    dfs_to_merge.append(df)

# マージ
from functools import reduce
df_merged = reduce(
    lambda l, r: pd.merge(l, r, on="trade_date", how="inner"),
    dfs_to_merge
)

# カスタムウェイトで合成
port_cols = [f"port_ret_cc_h{h}" for h in ENSEMBLE_CONFIG.keys()]
alpha_cols = [f"rel_alpha_h{h}" for h in ENSEMBLE_CONFIG.keys()]
weights = [ENSEMBLE_CONFIG[h]["weight"] for h in ENSEMBLE_CONFIG.keys()]

# ウェイト付き平均
df_merged["port_ret_cc_ens"] = (
    df_merged[port_cols].mul(weights, axis=1).sum(axis=1)
)
df_merged["rel_alpha_ens"] = (
    df_merged[alpha_cols].mul(weights, axis=1).sum(axis=1)
)

# TOPIXデータを取得（最初のホライゾンから）
first_h = sorted(ENSEMBLE_CONFIG.keys())[0]
df_first = horizon_results[first_h]
if "tpx_ret_cc" in df_first.columns:
    df_tpx = df_first[["trade_date", "tpx_ret_cc"]].copy()
    df_merged = df_merged.merge(df_tpx, on="trade_date", how="left")
else:
    # TOPIXデータを読み込み
    tpx_path = Path("data/processed/index_tpx_daily.parquet")
    if tpx_path.exists():
        df_tpx = pd.read_parquet(tpx_path)
        df_merged = df_merged.merge(
            df_tpx[["trade_date", "tpx_ret_cc"]],
            on="trade_date",
            how="left"
        )
    else:
        print("警告: TOPIXデータが見つかりません")

# 累積リターンも計算
df_merged["cum_port_ens"] = (1.0 + df_merged["port_ret_cc_ens"]).cumprod()
if "tpx_ret_cc" in df_merged.columns:
    df_merged["cum_tpx"] = (1.0 + df_merged["tpx_ret_cc"]).cumprod()

# 保存
out_path = Path("data/processed/horizon_ensemble_custom.parquet")
out_path.parent.mkdir(parents=True, exist_ok=True)
df_merged.to_parquet(out_path, index=False)
print(f"  アンサンブル完了: {len(df_merged)} 日分")
print(f"  ✓ 保存先: {out_path}")

# アンサンブル版の相対αを計算
df_ens_alpha = df_merged[["trade_date", "port_ret_cc_ens", "rel_alpha_ens", "tpx_ret_cc", "cum_port_ens", "cum_tpx"]].copy()
df_ens_alpha = df_ens_alpha.rename(columns={
    "port_ret_cc_ens": "port_ret_cc",
    "rel_alpha_ens": "rel_alpha_daily",
    "cum_port_ens": "cum_port"
})

# アンサンブル版の月次・年次集計
print("  アンサンブル版の月次・年次集計中...")
ensemble_monthly, ensemble_yearly = compute_monthly_perf(
    df_ens_alpha,
    label="custom_ensemble",
    out_prefix="data/processed/horizon"
)

# アンサンブル版のパフォーマンス表示
horizon_str = ",".join([f"H{h}({'L' if cfg['ladder'] else 'NL'})" for h, cfg in sorted(ENSEMBLE_CONFIG.items())])
print(f"\n=== Custom Ensemble ({horizon_str}) Performance ===")
print_horizon_performance(df_ens_alpha, 0, ensemble_monthly, ensemble_yearly)

# アンサンブル版の年率シャープレシオ（総合）を計算
ret = df_ens_alpha["port_ret_cc"]
mu_daily = ret.mean()
sigma_daily = ret.std()
sharpe_annual = (mu_daily * 252) / (sigma_daily * np.sqrt(252)) if sigma_daily > 0 else float("nan")
print(f"\nEnsemble annual Sharpe (total): {sharpe_annual:.4f}")

# サマリテーブル表示
if summary_rows:
    df_summary = pd.DataFrame(summary_rows)
    print("\n=== ホライゾン別パフォーマンスサマリ ===")
    display_cols = ["horizon", "ladder", "weight", "days", "total_port", "total_tpx", "total_alpha", 
                   "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown", "weight"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    display_df["ladder"] = display_df["ladder"].apply(lambda x: "ラダー" if x else "非ラダー")
    print(display_df.to_string(index=False))

print("\n" + "=" * 80)
print("=== カスタムウェイトアンサンブル完了 ===")
print("=" * 80)

