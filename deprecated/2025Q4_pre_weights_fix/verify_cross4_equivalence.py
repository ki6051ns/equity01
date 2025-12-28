#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/verify_cross4_equivalence.py

weights→returnsで得たcross4リターンが、既存horizon_ensemble_variant_cross4.parquet（return合成）と一致することを検証

比較対象:
A: 既存 ensemble_variant_cross4.py 出力（return合成）
B: 新 backtest_from_weights.py 出力（weights→returns）

成果物:
- research/reports/cross4_weights_equivalence.csv
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/verify_cross4_equivalence.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from typing import Tuple

DATA_DIR = Path("data/processed")
RESEARCH_DIR = Path("research/reports")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

# 許容誤差
TOLERANCE = 1e-8


def load_return_synthetic_cross4() -> pd.DataFrame:
    """
    既存のreturn合成cross4を読み込む
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"既存のcross4ファイルが見つかりません: {path}\n"
            "先に ensemble_variant_cross4.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    
    # trade_dateをdatetimeに変換
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    return df


def load_weights_synthetic_cross4() -> pd.DataFrame:
    """
    weights→returnsで生成したcross4を読み込む
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    path = DATA_DIR / "weights_bt" / "cross4_from_weights.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"weights版cross4ファイルが見つかりません: {path}\n"
            "先に backtest_from_weights.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    
    # trade_dateをdatetimeに変換
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    return df


def verify_equivalence(
    df_return_synthetic: pd.DataFrame,
    df_weights_synthetic: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    2つのcross4リターンが一致するかを検証
    
    Parameters
    ----------
    df_return_synthetic : pd.DataFrame
        既存のreturn合成cross4
    df_weights_synthetic : pd.DataFrame
        weights→returnsで生成したcross4
    
    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        (検証結果DataFrame, 詳細差分DataFrame)
    """
    # trade_dateでマージ
    df_merged = pd.merge(
        df_return_synthetic[["trade_date", "port_ret_cc"]].rename(columns={"port_ret_cc": "port_ret_cc_return_synthetic"}),
        df_weights_synthetic[["trade_date", "port_ret_cc"]].rename(columns={"port_ret_cc": "port_ret_cc_weights_synthetic"}),
        on="trade_date",
        how="inner"
    )
    
    if df_merged.empty:
        return pd.DataFrame(columns=["metric", "value", "status"])
    
    # 差分を計算
    df_merged["diff"] = df_merged["port_ret_cc_return_synthetic"] - df_merged["port_ret_cc_weights_synthetic"]
    df_merged["abs_diff"] = df_merged["diff"].abs()
    
    # 累積リターンを計算
    df_merged["cumret_return_synthetic"] = (1.0 + df_merged["port_ret_cc_return_synthetic"]).cumprod()
    df_merged["cumret_weights_synthetic"] = (1.0 + df_merged["port_ret_cc_weights_synthetic"]).cumprod()
    df_merged["cumret_diff"] = df_merged["cumret_return_synthetic"] - df_merged["cumret_weights_synthetic"]
    
    # 統計量を計算
    results = []
    
    # 日次差分
    mean_abs_diff = df_merged["abs_diff"].mean()
    max_abs_diff = df_merged["abs_diff"].max()
    results.append({
        "metric": "mean_abs_diff_daily",
        "value": mean_abs_diff,
        "status": "PASS" if mean_abs_diff < TOLERANCE else "FAIL"
    })
    results.append({
        "metric": "max_abs_diff_daily",
        "value": max_abs_diff,
        "status": "PASS" if max_abs_diff < TOLERANCE else "FAIL"
    })
    
    # 累積リターン差分（最終日）
    cumret_diff_last = df_merged["cumret_diff"].iloc[-1]
    results.append({
        "metric": "cumret_diff_last",
        "value": cumret_diff_last,
        "status": "PASS" if abs(cumret_diff_last) < TOLERANCE else "FAIL"
    })
    
    # 期間
    results.append({
        "metric": "period_start",
        "value": df_merged["trade_date"].min(),
        "status": "INFO"
    })
    results.append({
        "metric": "period_end",
        "value": df_merged["trade_date"].max(),
        "status": "INFO"
    })
    results.append({
        "metric": "num_days",
        "value": len(df_merged),
        "status": "INFO"
    })
    
    # 全体判定
    all_pass = all(r["status"] == "PASS" for r in results if r["status"] != "INFO")
    results.append({
        "metric": "overall",
        "value": "PASS" if all_pass else "FAIL",
        "status": "PASS" if all_pass else "FAIL"
    })
    
    df_results = pd.DataFrame(results)
    
    return df_results, df_merged


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== cross4 Equivalence検証（return合成 vs weights→returns） ===")
    print("=" * 80)
    
    # 既存のreturn合成cross4を読み込む
    print("\n[STEP 1] 既存のreturn合成cross4を読み込み中...")
    try:
        df_return_synthetic = load_return_synthetic_cross4()
        print(f"  ✓ {len(df_return_synthetic)} 日分")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return
    
    # weights→returnsで生成したcross4を読み込む
    print("\n[STEP 2] weights→returnsで生成したcross4を読み込み中...")
    try:
        df_weights_synthetic = load_weights_synthetic_cross4()
        print(f"  ✓ {len(df_weights_synthetic)} 日分")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return
    
    # 検証
    print("\n[STEP 3] 一致検証を実行中...")
    df_results, df_merged = verify_equivalence(df_return_synthetic, df_weights_synthetic)
    
    if df_results.empty:
        print("  ✗ 検証に失敗しました。")
        return
    
    # 結果を表示
    print("\n[検証結果]")
    for _, row in df_results.iterrows():
        status_icon = "✓" if row["status"] == "PASS" else "✗" if row["status"] == "FAIL" else "ℹ"
        print(f"  {status_icon} {row['metric']}: {row['value']} ({row['status']})")
    
    # 保存
    output_path = RESEARCH_DIR / "cross4_weights_equivalence.csv"
    df_results.to_csv(output_path, index=False)
    print(f"\n✓ 検証結果を保存: {output_path}")
    
    # 詳細差分も保存（オプション）
    detail_path = RESEARCH_DIR / "cross4_weights_equivalence_detail.parquet"
    df_merged.to_parquet(detail_path, index=False)
    print(f"✓ 詳細差分を保存: {detail_path}")
    
    # 差分が大きい日top20をCSVに出力
    df_merged_sorted = df_merged.sort_values("abs_diff", ascending=False)
    top20_path = RESEARCH_DIR / "cross4_weights_equivalence_top20_diff.csv"
    df_merged_sorted.head(20).to_csv(top20_path, index=False)
    print(f"✓ 差分が大きい日top20を保存: {top20_path}")
    
    # その日のweights上位銘柄もダンプ（検証用）
    if len(df_merged_sorted) > 0:
        # 最も差分が大きい日を特定
        top_diff_date = df_merged_sorted.iloc[0]["trade_date"]
        
        # その日のweightsを読み込む（検証用）
        # ファイル名を固定: data/processed/weights/cross4_target_weights.parquet
        # build_cross4_target_weights.pyの出力と一致させる
        weights_path = DATA_DIR / "weights" / "cross4_target_weights.parquet"
        if weights_path.exists():
            df_weights_all = pd.read_parquet(weights_path)
            df_weights_all["date"] = pd.to_datetime(df_weights_all["date"])
            df_weights_day = df_weights_all[df_weights_all["date"] == top_diff_date].copy()
            
            if not df_weights_day.empty:
                weights_dump_path = RESEARCH_DIR / f"cross4_weights_top_diff_date_{top_diff_date.strftime('%Y%m%d')}.csv"
                df_weights_day.sort_values("weight", ascending=False).head(30).to_csv(weights_dump_path, index=False)
                print(f"✓ 差分最大日のweights上位30銘柄を保存: {weights_dump_path}")
        
        # rank_onlyとzdownvolのweightsも読み込む（検証用）
        for variant in ["rank_only", "zdownvol"]:
            # 各horizonのweightsを読み込んで合成（簡易版）
            variant_weights = []
            for h in [1, 5, 10, 60, 90, 120]:
                ladder_type = "ladder" if h >= 60 else "nonladder"
                variant_path = DATA_DIR / "weights" / f"h{h}_{ladder_type}_{variant}.parquet"
                if variant_path.exists():
                    df_h = pd.read_parquet(variant_path)
                    df_h["date"] = pd.to_datetime(df_h["date"])
                    df_h_day = df_h[df_h["date"] == top_diff_date].copy()
                    if not df_h_day.empty:
                        variant_weights.append(df_h_day)
            
            if variant_weights:
                df_variant_all = pd.concat(variant_weights, ignore_index=True)
                df_variant_agg = df_variant_all.groupby("symbol")["weight"].sum().reset_index()
                df_variant_agg = df_variant_agg.sort_values("weight", ascending=False)
                variant_dump_path = RESEARCH_DIR / f"cross4_weights_{variant}_top_diff_date_{top_diff_date.strftime('%Y%m%d')}.csv"
                df_variant_agg.head(30).to_csv(variant_dump_path, index=False)
                print(f"✓ 差分最大日の{variant} weights上位30銘柄を保存: {variant_dump_path}")
    
    # 全体判定
    overall_status = df_results[df_results["metric"] == "overall"]["status"].iloc[0]
    if overall_status == "PASS":
        print("\n" + "=" * 80)
        print("✓ PASS: weights版cross4は既存のreturn合成cross4と一致しました")
        print("  → 旧analysis（return合成cross4）は不要化可能です")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("✗ FAIL: weights版cross4と既存のreturn合成cross4に差分があります")
        print("  → 詳細を確認してください")
        print("=" * 80)
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

