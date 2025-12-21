#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/analyze_cross4_cumret_diff_monthly.py

cross4_returns_comparison_detail.parquetを集計して、
累積リターンの差が何年の何月に広がったかを把握するスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/analyze_cross4_cumret_diff_monthly.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")
RESEARCH_DIR = Path("research/reports")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)


def load_comparison_detail() -> pd.DataFrame:
    """
    cross4_returns_comparison_detail.parquetを読み込む
    
    Returns
    -------
    pd.DataFrame
        trade_date, cumret_return, cumret_weights, cumret_diff を含むDataFrame
    """
    path = RESEARCH_DIR / "cross4_returns_comparison_detail.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"比較詳細ファイルが見つかりません: {path}\n"
            "先に compare_cross4_returns.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    
    # trade_dateをdatetimeに変換
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    return df


def calculate_monthly_cumret_diff(df: pd.DataFrame) -> pd.DataFrame:
    """
    月次で累積リターン差分を集計
    
    Parameters
    ----------
    df : pd.DataFrame
        trade_date, cumret_return, cumret_weights, cumret_diff を含むDataFrame
    
    Returns
    -------
    pd.DataFrame
        月次集計結果（年月、月初/月末の差分、月内変化量など）
    """
    df = df.copy().sort_values("trade_date")
    
    # 年月を抽出
    df["year"] = df["trade_date"].dt.year
    df["month"] = df["trade_date"].dt.month
    df["year_month"] = df["trade_date"].dt.to_period("M")
    
    # 月次で集計
    monthly_stats = []
    
    for year_month, group in df.groupby("year_month"):
        if len(group) == 0:
            continue
        
        # 月初と月末の差分
        cumret_diff_start = group["cumret_diff"].iloc[0]
        cumret_diff_end = group["cumret_diff"].iloc[-1]
        cumret_diff_change = cumret_diff_end - cumret_diff_start
        
        # 月内の最大・最小差分
        cumret_diff_max = group["cumret_diff"].max()
        cumret_diff_min = group["cumret_diff"].min()
        cumret_diff_range = cumret_diff_max - cumret_diff_min
        
        # 累積リターンの値（参考用）
        cumret_return_start = group["cumret_return"].iloc[0]
        cumret_return_end = group["cumret_return"].iloc[-1]
        cumret_weights_start = group["cumret_weights"].iloc[0]
        cumret_weights_end = group["cumret_weights"].iloc[-1]
        
        monthly_stats.append({
            "year": year_month.year,
            "month": year_month.month,
            "year_month": str(year_month),
            "日数": len(group),
            "月初_累積リターン差分": cumret_diff_start,
            "月末_累積リターン差分": cumret_diff_end,
            "月内変化量": cumret_diff_change,
            "月内最大差分": cumret_diff_max,
            "月内最小差分": cumret_diff_min,
            "月内範囲": cumret_diff_range,
            "月初_return合成累積": cumret_return_start,
            "月末_return合成累積": cumret_return_end,
            "月初_weights累積": cumret_weights_start,
            "月末_weights累積": cumret_weights_end,
        })
    
    df_monthly = pd.DataFrame(monthly_stats)
    
    return df_monthly.sort_values(["year", "month"]).reset_index(drop=True)


def identify_diff_expansion_periods(df_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    累積リターン差分が広がった期間を特定
    
    Parameters
    ----------
    df_monthly : pd.DataFrame
        月次集計結果（変化量_絶対値列を含む）
    
    Returns
    -------
    pd.DataFrame
        差分が広がった期間のリスト（変化量が大きい順）
    """
    # 月内変化量の絶対値が大きい順にソート
    df_expansion = df_monthly.copy()
    if "変化量_絶対値" not in df_expansion.columns:
        df_expansion["変化量_絶対値"] = df_expansion["月内変化量"].abs()
    df_expansion = df_expansion.sort_values("変化量_絶対値", ascending=False)
    
    return df_expansion


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== cross4 累積リターン差分 月次分析 ===")
    print("=" * 80)
    
    # 比較詳細データを読み込む
    print("\n[STEP 1] 比較詳細データを読み込み中...")
    try:
        df_detail = load_comparison_detail()
        print(f"  ✓ {len(df_detail)} 日分")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 月次集計
    print("\n[STEP 2] 月次集計を計算中...")
    df_monthly = calculate_monthly_cumret_diff(df_detail)
    print(f"  ✓ {len(df_monthly)} か月分")
    
    # 変化量_絶対値を追加（年次集計のため）
    df_monthly["変化量_絶対値"] = df_monthly["月内変化量"].abs()
    
    # 差分拡大期間を特定
    print("\n[STEP 3] 差分拡大期間を特定中...")
    df_expansion = identify_diff_expansion_periods(df_monthly)
    
    # 結果を表示
    print("\n" + "=" * 80)
    print("【月次累積リターン差分 集計結果】")
    print("=" * 80)
    
    # 全体サマリ
    print(f"\n期間: {df_monthly['year_month'].iloc[0]} ～ {df_monthly['year_month'].iloc[-1]}")
    print(f"総月数: {len(df_monthly)} か月")
    print(f"最終月の累積リターン差分: {df_monthly['月末_累積リターン差分'].iloc[-1]:.8f}")
    
    # 差分が広がった月Top20
    print("\n" + "=" * 80)
    print("【累積リターン差分が広がった月 Top20（変化量の絶対値順）】")
    print("=" * 80)
    
    top20 = df_expansion.head(20)[[
        "year_month",
        "月初_累積リターン差分",
        "月末_累積リターン差分",
        "月内変化量",
        "変化量_絶対値",
        "日数"
    ]]
    
    for idx, row in top20.iterrows():
        change_sign = "↑拡大" if row["月内変化量"] > 0 else "↓縮小"
        print(f"\n{row['year_month']}: {change_sign}")
        print(f"  月初差分: {row['月初_累積リターン差分']:.8f}")
        print(f"  月末差分: {row['月末_累積リターン差分']:.8f}")
        print(f"  変化量: {row['月内変化量']:.8f} (絶対値: {row['変化量_絶対値']:.8f})")
        print(f"  日数: {row['日数']} 日")
    
    # 年ごとの集計
    print("\n" + "=" * 80)
    print("【年ごとの累積リターン差分 変化量】")
    print("=" * 80)
    
    yearly_change = df_monthly.groupby("year").agg({
        "月内変化量": ["sum", "mean", "std"],
        "変化量_絶対値": ["sum", "mean"],
        "日数": "sum"
    }).round(8)
    
    yearly_change.columns = ["年間変化量_合計", "年間変化量_平均", "年間変化量_標準偏差", "年間変化量_絶対値合計", "年間変化量_絶対値平均", "年間総日数"]
    yearly_change = yearly_change.reset_index()
    
    for _, row in yearly_change.iterrows():
        print(f"\n{int(row['year'])}年:")
        print(f"  年間変化量合計: {row['年間変化量_合計']:.8f}")
        print(f"  年間変化量平均: {row['年間変化量_平均']:.8f}")
        print(f"  年間変化量標準偏差: {row['年間変化量_標準偏差']:.8f}")
        print(f"  年間変化量絶対値合計: {row['年間変化量_絶対値合計']:.8f}")
        print(f"  年間総日数: {int(row['年間総日数'])} 日")
    
    # 保存
    output_monthly = RESEARCH_DIR / "cross4_cumret_diff_monthly.csv"
    df_monthly.to_csv(output_monthly, index=False, encoding='utf-8-sig')
    print(f"\n✓ 月次集計結果を保存: {output_monthly}")
    
    output_expansion = RESEARCH_DIR / "cross4_cumret_diff_expansion_periods.csv"
    df_expansion.to_csv(output_expansion, index=False, encoding='utf-8-sig')
    print(f"✓ 差分拡大期間を保存: {output_expansion}")
    
    output_yearly = RESEARCH_DIR / "cross4_cumret_diff_yearly.csv"
    yearly_change.to_csv(output_yearly, index=False, encoding='utf-8-sig')
    print(f"✓ 年次集計結果を保存: {output_yearly}")
    
    print("\n" + "=" * 80)
    print("完了: cross4 累積リターン差分 月次分析完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

