"""
Variant-Cross Ensemble4（Variant横断アンサンブル4）を生成するスクリプト

全ホライゾン（H1, H5, H10, H60, H90, H120）: Variant B 75% / E 25%（rank_only 75%, z_downvol 25%）

その後、ホライゾン間で指定ウェイトで合成

指定ウェイト:
- H1: 0.15（非ラダー）
- H5: 0.15（非ラダー）
- H10: 0.20（非ラダー）
- H60: 0.10（ラダー）
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
    (1, "nonladder"): 0.15,
    (5, "nonladder"): 0.15,
    (10, "nonladder"): 0.20,
    (60, "ladder"): 0.10,
    (90, "ladder"): 0.20,
    (120, "ladder"): 0.20,
}

# Variant定義（全ホライゾン共通）
VARIANTS = {
    "rank": "rank_only (Variant B)",
    "zdownvol": "z_downvol (Variant E)",
}

# Variant内ウェイト（B 75% / E 25%）
VARIANT_WEIGHTS = {
    "rank": 0.75,  # Variant B (rank_only)
    "zdownvol": 0.25,  # Variant E (z_downvol)
}

# ウェイトの合計が1.0か確認
total_weight = sum(WEIGHTS.values())
if abs(total_weight - 1.0) > 1e-6:
    print(f"警告: ウェイトの合計が1.0ではありません: {total_weight}")
    print("正規化します...")
    for key in WEIGHTS:
        WEIGHTS[key] /= total_weight

# Variant内ウェイトの合計が1.0か確認
total_variant_weight = sum(VARIANT_WEIGHTS.values())
if abs(total_variant_weight - 1.0) > 1e-6:
    print(f"警告: Variant内ウェイトの合計が1.0ではありません: {total_variant_weight}")
    print("正規化します...")
    for key in VARIANT_WEIGHTS:
        VARIANT_WEIGHTS[key] /= total_variant_weight

print("=" * 80)
print("=== Variant-Cross Ensemble4（Variant横断アンサンブル4） ===")
print("=" * 80)
print("\nアンサンブル設定:")
print("\nVariant内ウェイト:")
for variant_key, w in sorted(VARIANT_WEIGHTS.items()):
    variant_name = VARIANTS.get(variant_key, variant_key)
    print(f"  {variant_name}: {w:.2%}")

print("\n全ホライゾン（Variant B 75% / E 25%）:")
for (h, lad), w in sorted(WEIGHTS.items()):
    mode = "ラダー" if lad == "ladder" else "非ラダー"
    print(f"  H{h} ({mode}): {w:.2%}")
print(f"\n合計: {sum(WEIGHTS.values()):.2%}")


def load_horizon_variant_data(h: int, ladder_type: str, variant_key: str) -> pd.DataFrame:
    """
    ホライゾン×Variantのバックテスト結果を読み込む
    
    Parameters
    ----------
    h : int
        ホライゾン
    ladder_type : str
        "ladder" または "nonladder"
    variant_key : str
        Variantキー（"rank", "zdownvol"）
    
    Returns
    -------
    pd.DataFrame
        バックテスト結果（trade_date, port_ret_cc を含む）
    """
    # ファイル名のパターン
    suffix_map = {
        "rank": "rank",
        "zdownvol": "zdownvol",
    }
    
    suffix = suffix_map.get(variant_key, variant_key)
    pt_path = DATA_DIR / f"paper_trade_h{h}_{ladder_type}_{suffix}.parquet"
    alpha_path = DATA_DIR / f"paper_trade_with_alpha_beta_h{h}_{ladder_type}_{suffix}.parquet"
    
    if alpha_path.exists():
        df = pd.read_parquet(alpha_path)
        if len(df) > 0:
            return df
    elif pt_path.exists():
        # alpha計算がまだなら実行
        df_pt = pd.read_parquet(pt_path)
        if len(df_pt) > 0:
            df = calc_alpha_beta_for_horizon(df_pt, h)
            # ファイル名を修正（非ラダー版の場合）
            if ladder_type == "nonladder":
                alpha_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(alpha_path, index=False)
            return df
    
    return pd.DataFrame()


def average_variants_for_horizon(h: int, ladder_type: str, variant_dict: dict, variant_weights: dict) -> pd.DataFrame:
    """
    ホライゾン内で複数のVariantを重み付き平均化（B 75% / E 25%）
    
    Parameters
    ----------
    h : int
        ホライゾン
    ladder_type : str
        "ladder" または "nonladder"
    variant_dict : dict
        Variant辞書
    variant_weights : dict
        Variant内ウェイト（{"rank": 0.75, "zdownvol": 0.25}）
    
    Returns
    -------
    pd.DataFrame
        重み付き平均化されたバックテスト結果
    """
    dfs = {}
    loaded_variants = []
    
    for variant_key, variant_name in variant_dict.items():
        df = load_horizon_variant_data(h, ladder_type, variant_key)
        if not df.empty:
            dfs[variant_key] = df
            loaded_variants.append(f"{variant_name} ({variant_weights.get(variant_key, 0.0):.0%})")
    
    if len(dfs) == 0:
        print(f"  ⚠️  H{h} ({ladder_type}): 読み込めるVariantがありません")
        return pd.DataFrame()
    
    print(f"  H{h} ({ladder_type}): {len(loaded_variants)} Variantを重み付き平均化 ({', '.join(loaded_variants)})")
    
    # 日付でマージ
    merged = None
    for variant_key, df in dfs.items():
        weight = variant_weights.get(variant_key, 0.0)
        if weight > 0:
            df_weighted = df[["trade_date", "port_ret_cc"]].copy()
            df_weighted["port_ret_cc"] = df_weighted["port_ret_cc"] * weight
            
            if merged is None:
                merged = df_weighted
            else:
                merged = pd.merge(merged, df_weighted, on="trade_date", how="outer", suffixes=("", f"_{variant_key}"))
    
    if merged is None:
        return pd.DataFrame()
    
    # 重み付き平均を計算
    ret_cols = [c for c in merged.columns if c.startswith("port_ret_cc")]
    if len(ret_cols) > 0:
        merged["port_ret_cc"] = merged[ret_cols].sum(axis=1)
        merged = merged.drop(columns=[c for c in ret_cols if c != "port_ret_cc"])
    
    # TOPIXデータを取得（最初のVariantから）
    first_variant_key = list(dfs.keys())[0]
    df_first = dfs[first_variant_key]
    if "tpx_ret_cc" in df_first.columns:
        df_tpx = df_first[["trade_date", "tpx_ret_cc"]].copy()
        merged = merged.merge(df_tpx, on="trade_date", how="left")
        merged["tpx_ret_cc"] = merged["tpx_ret_cc"].ffill().bfill()
    else:
        merged["tpx_ret_cc"] = 0.0
    
    # 相対αを再計算
    merged["rel_alpha_daily"] = merged["port_ret_cc"] - merged["tpx_ret_cc"]
    
    return merged.sort_values("trade_date").reset_index(drop=True)


def load_horizon_ensemble_data(h: int, ladder_type: str) -> pd.DataFrame:
    """
    ホライゾンのアンサンブルデータを読み込む（Variant重み付き平均化済み）
    
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
    return average_variants_for_horizon(h, ladder_type, VARIANTS, VARIANT_WEIGHTS)


def calculate_horizon_summary(df_alpha: pd.DataFrame, h: int) -> dict:
    """
    ホライゾンのサマリを計算
    """
    if df_alpha.empty:
        return {
            "horizon": h,
            "total_port": 0.0,
            "total_tpx": 0.0,
            "total_alpha": 0.0,
            "alpha_sharpe_annual": np.nan,
            "max_drawdown": np.nan,
            "days": 0,
        }
    
    return summarize_horizon(df_alpha, h)


print("\n[STEP 1] 各ホライゾンのVariant重み付き平均化中...")
horizon_data = {}
horizon_summaries = []

for (h, ladder_type), weight in sorted(WEIGHTS.items()):
    print(f"\n  H{h} ({ladder_type}) 処理中...")
    df = load_horizon_ensemble_data(h, ladder_type)
    
    if df.empty:
        print(f"  ⚠️  H{h} ({ladder_type}): データが空です")
        continue
    
    horizon_data[(h, ladder_type)] = df
    summary = calculate_horizon_summary(df, h)
    summary["weight"] = weight
    summary["ladder"] = ladder_type == "ladder"
    horizon_summaries.append(summary)
    
    print(
        f"  ✓ H{h} ({ladder_type}): {len(df)} 日分, "
        f"total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"weight={weight:.2%}"
    )

if not horizon_data:
    print("\n⚠️  読み込めるデータがありませんでした。")
    print("先に run_all_*.py スクリプトを実行してバックテスト結果を生成してください。")
    sys.exit(1)

# 空のデータを除外してウェイトを再正規化
valid_weights = {k: v for k, v in WEIGHTS.items() if k in horizon_data}
if len(valid_weights) < len(WEIGHTS):
    print(f"\n⚠️  {len(WEIGHTS) - len(valid_weights)} ホライゾンのデータが欠落しています。")
    print("ウェイトを再正規化します...")
    total_valid = sum(valid_weights.values())
    if total_valid > 0:
        for k in valid_weights:
            valid_weights[k] /= total_valid
    WEIGHTS = valid_weights

print("\n[STEP 2] ホライゾン間アンサンブル合成中...")

# 日付でマージ
dfs_to_merge = []
tpx_df = None  # TOPIXデータは最初のDataFrameから取得
for (h, ladder_type), df in horizon_data.items():
    weight = WEIGHTS.get((h, ladder_type), 0.0)
    if weight > 0 and not df.empty:
        # rel_alpha_daily が存在しない場合は計算
        if "rel_alpha_daily" not in df.columns:
            df["rel_alpha_daily"] = df["port_ret_cc"] - df["tpx_ret_cc"]
        
        # TOPIXデータは最初のDataFrameから取得（一度だけ）
        if tpx_df is None and "tpx_ret_cc" in df.columns:
            tpx_df = df[["trade_date", "tpx_ret_cc"]].copy()
        
        # tpx_ret_cc は含めず、port_ret_cc と rel_alpha_daily のみ
        df_weighted = df[["trade_date", "port_ret_cc", "rel_alpha_daily"]].copy()
        df_weighted["port_ret_cc"] = df_weighted["port_ret_cc"] * weight
        df_weighted["rel_alpha_daily"] = df_weighted["rel_alpha_daily"] * weight
        df_weighted = df_weighted.rename(columns={
            "port_ret_cc": f"ret_h{h}_{ladder_type}",
            "rel_alpha_daily": f"alpha_h{h}_{ladder_type}",
        })
        dfs_to_merge.append(df_weighted)

if not dfs_to_merge:
    print("⚠️  マージできるデータがありません。")
    sys.exit(1)

# マージ
merged = reduce(
    lambda l, r: pd.merge(l, r, on="trade_date", how="outer"),
    dfs_to_merge
).fillna(0.0)

# アンサンブルリターン計算
ret_cols = [c for c in merged.columns if c.startswith("ret_h")]
alpha_cols = [c for c in merged.columns if c.startswith("alpha_h")]
merged["port_ret_cc"] = merged[ret_cols].sum(axis=1)
merged["rel_alpha_daily"] = merged[alpha_cols].sum(axis=1) if len(alpha_cols) > 0 else 0.0

# tpx_ret_cc を追加（最初のDataFrameから取得）
if tpx_df is not None:
    merged = merged.merge(tpx_df, on="trade_date", how="left")
    merged["tpx_ret_cc"] = merged["tpx_ret_cc"].fillna(0.0)
else:
    # フォールバック: 最初のホライゾンから取得
    first_key = sorted(horizon_data.keys())[0]
    df_first = horizon_data[first_key]
    if "tpx_ret_cc" in df_first.columns:
        df_tpx = df_first[["trade_date", "tpx_ret_cc"]].copy()
        merged = merged.merge(df_tpx, on="trade_date", how="left")
        merged["tpx_ret_cc"] = merged["tpx_ret_cc"].fillna(0.0)
    else:
        # それでも取得できない場合は0で埋める
        merged["tpx_ret_cc"] = 0.0

# 累積リターン計算
merged["cumulative_port"] = (1.0 + merged["port_ret_cc"]).cumprod()
merged["cumulative_tpx"] = (1.0 + merged["tpx_ret_cc"]).cumprod() if "tpx_ret_cc" in merged.columns else pd.Series(1.0, index=merged.index)
merged["cumulative_alpha"] = merged["cumulative_port"] - merged["cumulative_tpx"]

print(f"  合成完了: {len(merged)} 日分")

# サマリ計算
ensemble_summary = {
    "total_port": merged["cumulative_port"].iloc[-1] - 1.0 if len(merged) > 0 else 0.0,
    "total_tpx": merged["cumulative_tpx"].iloc[-1] - 1.0 if len(merged) > 0 else 0.0,
    "total_alpha": merged["cumulative_alpha"].iloc[-1] if len(merged) > 0 else 0.0,
    "days": len(merged),
}

# シャープレシオ計算
if len(merged) > 0 and "rel_alpha_daily" in merged.columns and merged["rel_alpha_daily"].std() > 0:
    annual_factor = np.sqrt(252)
    ensemble_summary["alpha_sharpe_annual"] = (
        merged["rel_alpha_daily"].mean() / merged["rel_alpha_daily"].std() * annual_factor
    )
else:
    ensemble_summary["alpha_sharpe_annual"] = np.nan

# 最大ドローダウン計算
if len(merged) > 0:
    cumulative = merged["cumulative_port"]
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    ensemble_summary["max_drawdown"] = drawdown.min()
else:
    ensemble_summary["max_drawdown"] = np.nan

print("\n" + "=" * 80)
print("=== Variant-Cross Ensemble4 パフォーマンス ===")
print("=" * 80)
print(f"累積: Port {ensemble_summary['total_port']:+.2%}, "
      f"TOPIX {ensemble_summary['total_tpx']:+.2%}, "
      f"α {ensemble_summary['total_alpha']:+.2%}")
print(f"Sharpe(α): {ensemble_summary['alpha_sharpe_annual']:.2f}")
print(f"maxDD: {ensemble_summary['max_drawdown']:+.2%}")
print(f"期間: {merged['trade_date'].min()} ～ {merged['trade_date'].max()}")
print(f"日数: {ensemble_summary['days']}")

# ホライゾン別サマリ表示
if horizon_summaries:
    print("\n=== ホライゾン別パフォーマンスサマリ ===")
    df_summary = pd.DataFrame(horizon_summaries)
    display_cols = ["horizon", "ladder", "weight", "days", "total_port", "total_tpx", 
                   "total_alpha", "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown", "weight"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A")
    display_df["ladder"] = display_df["ladder"].apply(lambda x: "ラダー" if x else "非ラダー")
    print(display_df.to_string(index=False))

# 月次・年次パフォーマンス計算用のDataFrameを準備
df_perf = merged[["trade_date", "port_ret_cc", "tpx_ret_cc", "rel_alpha_daily"]].copy()

print("\n[STEP 3] 月次・年次パフォーマンス計算中...")
monthly, yearly = compute_monthly_perf(
    df_perf,
    label="variant_cross_ensemble4",
    out_prefix="data/processed/horizon"
)

# パフォーマンス表示
print_horizon_performance(df_perf, "Variant-Cross Ensemble4", monthly, yearly)

# 保存
output_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
merged.to_parquet(output_path, index=False)
print(f"\n✓ アンサンブル結果を保存: {output_path}")

print("\n" + "=" * 80)
print("=== Variant-Cross Ensemble4 完了 ===")
print("=" * 80)

