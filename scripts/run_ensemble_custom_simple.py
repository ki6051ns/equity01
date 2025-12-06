"""
カスタムウェイトアンサンブル（簡易版 - 既存ファイルから読み込む）
"""
import pandas as pd
import numpy as np
from pathlib import Path
from functools import reduce

# アンサンブル設定
ENSEMBLE_CONFIG = {
    1: {"weight": 0.10, "ladder": False},
    5: {"weight": 0.10, "ladder": False},
    10: {"weight": 0.20, "ladder": False},
    60: {"weight": 0.20, "ladder": True},
    90: {"weight": 0.20, "ladder": True},
    120: {"weight": 0.20, "ladder": True},
}

print("=" * 80)
print("=== カスタムウェイトアンサンブル（既存ファイルから） ===")
print("=" * 80)
print("\nアンサンブル設定:")
for h in sorted(ENSEMBLE_CONFIG.keys()):
    cfg = ENSEMBLE_CONFIG[h]
    mode = "ラダー" if cfg["ladder"] else "非ラダー"
    print(f"  H{h}: {cfg['weight']:.2%} ({mode})")

# 各ホライゾンの結果を読み込み
horizon_results = {}
summary_rows = []

for h, cfg in sorted(ENSEMBLE_CONFIG.items()):
    weight = cfg["weight"]
    is_ladder = cfg["ladder"]
    
    print(f"\n[H{h}] 結果を読み込み中... ({'ラダー' if is_ladder else '非ラダー'})")
    
    # ファイルパス
    if is_ladder:
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}.parquet")
    else:
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_nonladder_h{h}.parquet")
    
    if not alpha_path.exists():
        print(f"  [H{h}] 警告: {alpha_path} が見つかりません。スキップします。")
        continue
    
    df_alpha = pd.read_parquet(alpha_path)
    print(f"  [H{h}] 読み込み完了: {len(df_alpha)} 日分")
    
    # サマリ計算
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    cum_port = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cum_port.cummax()
    drawdown = (cum_port / rolling_max - 1.0).min()
    
    summary_rows.append({
        "horizon": h,
        "ladder": is_ladder,
        "weight": weight,
        "total_port": total_port,
        "total_alpha": total_alpha,
        "alpha_sharpe_annual": sharpe_alpha,
        "max_drawdown": drawdown,
    })
    
    print(
        f"  [H{h}] total_port={total_port:.2%}, "
        f"total_alpha={total_alpha:.2%}, "
        f"αSharpe={sharpe_alpha:.2f}, "
        f"max_dd={drawdown:.2%}"
    )
    
    horizon_results[h] = df_alpha

# アンサンブル計算
print("\n[STEP] カスタムウェイトアンサンブル実行中...")

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

# サマリ計算
df = df_ens_alpha.copy()
df = df.sort_values("trade_date")

total_port = (1 + df["port_ret_cc"]).prod() - 1
total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
total_alpha = total_port - total_tpx

mean_alpha = df["rel_alpha_daily"].mean()
std_alpha = df["rel_alpha_daily"].std()
sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")

cum_port = (1.0 + df["port_ret_cc"]).cumprod()
rolling_max = cum_port.cummax()
drawdown = (cum_port / rolling_max - 1.0).min()

# 年率統計
days = len(df)
years = days / 252.0
annual_return = (1 + total_port) ** (1.0 / years) - 1 if years > 0 else 0.0
annual_vol = df["port_ret_cc"].std() * np.sqrt(252)
sharpe_total = annual_return / annual_vol if annual_vol > 0 else float("nan")

print("\n" + "=" * 80)
print("=== Custom Ensemble Performance ===")
print("=" * 80)
print(f"累積: Port {total_port:+.4%}, TOPIX {total_tpx:+.4%}, α {total_alpha:+.4%}")
print(f"Sharpe(α): {sharpe_alpha:.2f}")
print(f"Sharpe(total): {sharpe_total:.2f}")
print(f"maxDD: {drawdown:+.4%}")
print(f"期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
print(f"日数: {len(df)}")
print(f"年率リターン: {annual_return:+.4%}")
print(f"年率ボラ: {annual_vol:+.4%}")

# サマリテーブル表示
if summary_rows:
    df_summary = pd.DataFrame(summary_rows)
    print("\n=== ホライゾン別パフォーマンスサマリ ===")
    display_cols = ["horizon", "ladder", "weight", "total_port", "total_alpha", 
                   "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_alpha", "max_drawdown", "weight"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    display_df["ladder"] = display_df["ladder"].apply(lambda x: "ラダー" if x else "非ラダー")
    print(display_df.to_string(index=False))

print("\n" + "=" * 80)
print("=== カスタムウェイトアンサンブル完了 ===")
print("=" * 80)

