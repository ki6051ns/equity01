"""
rank-only の指定ウェイトアンサンブルを生成するスクリプト

指定ウェイト:
- H1: 0.10（非ラダー）
- H5: 0.10（非ラダー）
- H10: 0.20（非ラダー）
- H60: 0.20（ラダー）
- H90: 0.20（ラダー）
- H120: 0.20（ラダー）
"""
import sys
from pathlib import Path
from functools import reduce

import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from horizon_ensemble import (
    calc_alpha_beta_for_horizon,
    summarize_horizon,
    compute_monthly_perf,
    print_horizon_performance,
)

DATA_DIR = Path("data/processed")

# 指定ウェイト
WEIGHTS = {
    (1, "nonladder"): 0.10,
    (5, "nonladder"): 0.10,
    (10, "nonladder"): 0.20,
    (60, "ladder"): 0.20,
    (90, "ladder"): 0.20,
    (120, "ladder"): 0.20,
}

# ウェイトの合計が1.0か確認
total_weight = sum(WEIGHTS.values())
if abs(total_weight - 1.0) > 1e-6:
    print(f"警告: ウェイトの合計が1.0ではありません: {total_weight}")
    print("正規化します...")
    for key in WEIGHTS:
        WEIGHTS[key] /= total_weight

print("=" * 80)
print("=== rank-only 指定ウェイトアンサンブル ===")
print("=" * 80)
print("\nアンサンブル設定:")
for (h, lad), w in sorted(WEIGHTS.items()):
    print(f"  H{h} ({lad}): {w:.2%}")
print(f"合計: {sum(WEIGHTS.values()):.2%}")

def load_horizon_data(h: int, ladder_type: str) -> pd.DataFrame:
    """
    ホライゾンのバックテスト結果を読み込む
    
    Parameters
    ----------
    h : int
        ホライゾン
    ladder_type : str
        "ladder" または "nonladder"
    
    Returns
    -------
    pd.DataFrame
        バックテスト結果（trade_date, port_ret_cc を含む）
    """
    # rank-only 版のファイルを読み込む
    pt_path = DATA_DIR / f"paper_trade_h{h}_{ladder_type}_rank.parquet"
    alpha_path = DATA_DIR / f"paper_trade_with_alpha_beta_h{h}_{ladder_type}_rank.parquet"
    
    if alpha_path.exists():
        df = pd.read_parquet(alpha_path)
        print(f"  H{h} ({ladder_type}): {len(df)} 日分を読み込み")
        return df
    elif pt_path.exists():
        # alpha計算がまだなら実行
        print(f"  H{h} ({ladder_type}): 相対α計算中...")
        df_pt = pd.read_parquet(pt_path)
        df = calc_alpha_beta_for_horizon(df_pt, h)
        # ファイル名を修正（非ラダー版の場合）
        if ladder_type == "nonladder":
            alpha_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(alpha_path, index=False)
        print(f"  H{h} ({ladder_type}): 相対α計算完了")
        return df
    else:
        raise FileNotFoundError(
            f"H{h} ({ladder_type}) のバックテスト結果が見つかりません: {pt_path} または {alpha_path}"
        )


def calculate_horizon_summary(df_alpha: pd.DataFrame, h: int) -> dict:
    """
    ホライゾン別のサマリを計算
    
    Parameters
    ----------
    df_alpha : pd.DataFrame
        相対α計算済みのDataFrame
    h : int
        ホライゾン
    
    Returns
    -------
    dict
        サマリ情報
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1 if "tpx_ret_cc" in df.columns else 0.0
    total_alpha = total_port - total_tpx
    
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    cum_port = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cum_port.cummax()
    drawdown = (cum_port / rolling_max - 1.0).min()
    
    return {
        "horizon": h,
        "total_port": total_port,
        "total_tpx": total_tpx,
        "total_alpha": total_alpha,
        "alpha_sharpe_annual": sharpe_alpha,
        "max_drawdown": drawdown,
        "days": len(df),
    }

# 各ホライゾンのデータを読み込む
print("\n[STEP 1] 各ホライゾンのバックテスト結果を読み込み中...")
horizon_dfs = {}
summary_rows = []
for (h, lad), w in sorted(WEIGHTS.items()):
    print(f"\n[H{h}] 結果を読み込み中... ({'ラダー' if lad == 'ladder' else '非ラダー'})")
    df = load_horizon_data(h, lad)
    horizon_dfs[(h, lad)] = df
    
    # サマリ計算
    summary = calculate_horizon_summary(df, h)
    summary["ladder"] = (lad == "ladder")
    summary["weight"] = w
    summary_rows.append(summary)
    
    print(
        f"  [H{h}] total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"max_dd={summary['max_drawdown']:.2%}"
    )

# 日付でマージ
print("\n[STEP 2] 日付でマージ中...")
dfs_to_merge = []
for (h, lad), df in sorted(horizon_dfs.items()):
    weight = WEIGHTS[(h, lad)]
    df_subset = df[["trade_date", "port_ret_cc", "rel_alpha_daily"]].copy()
    df_subset = df_subset.rename(columns={
        "port_ret_cc": f"port_ret_cc_h{h}_{lad}",
        "rel_alpha_daily": f"rel_alpha_h{h}_{lad}",
    })
    dfs_to_merge.append(df_subset)

# マージ
df_merged = reduce(
    lambda l, r: pd.merge(l, r, on="trade_date", how="inner"),
    dfs_to_merge
)
print(f"  マージ完了: {len(df_merged)} 日分")

# 指定ウェイトで合成
print("\n[STEP 3] 指定ウェイトでアンサンブル計算中...")
port_cols = [f"port_ret_cc_h{h}_{lad}" for (h, lad) in sorted(WEIGHTS.keys())]
alpha_cols = [f"rel_alpha_h{h}_{lad}" for (h, lad) in sorted(WEIGHTS.keys())]
weights = [WEIGHTS[(h, lad)] for (h, lad) in sorted(WEIGHTS.keys())]

# ウェイト付き平均
df_merged["port_ret_cc_ens"] = (
    df_merged[port_cols].mul(weights, axis=1).sum(axis=1)
)
df_merged["rel_alpha_ens"] = (
    df_merged[alpha_cols].mul(weights, axis=1).sum(axis=1)
)

# TOPIXデータを取得（最初のホライゾンから）
first_key = sorted(WEIGHTS.keys())[0]
df_first = horizon_dfs[first_key]
if "tpx_ret_cc" in df_first.columns:
    df_tpx = df_first[["trade_date", "tpx_ret_cc"]].copy()
    df_merged = df_merged.merge(df_tpx, on="trade_date", how="left")
else:
    # TOPIXデータを読み込み
    tpx_path = DATA_DIR / "index_tpx_daily.parquet"
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
out_path = DATA_DIR / "horizon_ensemble_rank_only.parquet"
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
print("\n[STEP 4] アンサンブル版の月次・年次集計中...")
ensemble_monthly, ensemble_yearly = compute_monthly_perf(
    df_ens_alpha,
    label="rank_only_ensemble",
    out_prefix="data/processed/horizon"
)

# アンサンブル版のパフォーマンス表示
horizon_str = ",".join([f"H{h}({'L' if lad == 'ladder' else 'NL'})" for (h, lad) in sorted(WEIGHTS.keys())])
print(f"\n=== rank-only Ensemble ({horizon_str}) Performance ===")
print_horizon_performance(df_ens_alpha, 0, ensemble_monthly, ensemble_yearly)

# アンサンブル版の詳細サマリ計算
df = df_ens_alpha.copy()
df = df.sort_values("trade_date")

total_port = (1 + df["port_ret_cc"]).prod() - 1
total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1 if "tpx_ret_cc" in df.columns else 0.0
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
print("=== rank-only Ensemble Performance ===")
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
    print("\n=== ホライゾン別パフォーマンスサマリ (rank-only) ===")
    display_cols = ["horizon", "ladder", "weight", "total_port", "total_alpha", 
                   "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_alpha", "max_drawdown", "weight"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    display_df["ladder"] = display_df["ladder"].apply(lambda x: "ラダー" if x else "非ラダー")
    print(display_df.to_string(index=False))

print("\n" + "=" * 80)
print("=== rank-only 指定ウェイトアンサンブル完了 ===")
print("=" * 80)
