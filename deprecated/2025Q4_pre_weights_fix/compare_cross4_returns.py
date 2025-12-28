#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/compare_cross4_returns.py

cross4_from_weights.parquet（weights版cross4）と
ensemble_variant_cross4.pyの実行結果（return合成cross4）を
分かりやすく比較して集計するスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/compare_cross4_returns.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = Path("data/processed")
RESEARCH_DIR = Path("research/reports")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)


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


def calculate_summary_stats(df: pd.DataFrame, label: str) -> dict:
    """
    リターン系列の統計を計算
    
    Parameters
    ----------
    df : pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    label : str
        ラベル名
    
    Returns
    -------
    dict
        統計情報の辞書
    """
    df = df.copy().sort_values("trade_date")
    
    # 累積リターン
    cumret = (1.0 + df["port_ret_cc"]).prod() - 1.0
    
    # 年率リターン
    days = (df["trade_date"].max() - df["trade_date"].min()).days
    years = days / 365.25
    annual_return = (1.0 + cumret) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    
    # 年率ボラティリティ
    daily_vol = df["port_ret_cc"].std()
    annual_vol = daily_vol * np.sqrt(252)
    
    # Sharpe比
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    
    # 最大ドローダウン
    cumulative = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative / rolling_max - 1.0).min()
    
    # 勝率
    win_rate = (df["port_ret_cc"] > 0).sum() / len(df) if len(df) > 0 else 0.0
    
    return {
        "label": label,
        "期間開始": df["trade_date"].min().strftime("%Y-%m-%d"),
        "期間終了": df["trade_date"].max().strftime("%Y-%m-%d"),
        "日数": len(df),
        "累積リターン": cumret,
        "年率リターン": annual_return,
        "年率ボラティリティ": annual_vol,
        "Sharpe比": sharpe,
        "最大ドローダウン": drawdown,
        "勝率": win_rate,
        "平均日次リターン": df["port_ret_cc"].mean(),
        "最大日次リターン": df["port_ret_cc"].max(),
        "最小日次リターン": df["port_ret_cc"].min(),
    }


def compare_returns(df_return: pd.DataFrame, df_weights: pd.DataFrame) -> pd.DataFrame:
    """
    2つのリターン系列を比較
    
    Parameters
    ----------
    df_return : pd.DataFrame
        既存のreturn合成cross4
    df_weights : pd.DataFrame
        weights→returnsで生成したcross4
    
    Returns
    -------
    pd.DataFrame
        比較結果のDataFrame
    """
    # 日付でマージ
    df_merged = df_return[["trade_date", "port_ret_cc"]].merge(
        df_weights[["trade_date", "port_ret_cc"]],
        on="trade_date",
        how="inner",
        suffixes=("_return", "_weights")
    )
    
    df_merged = df_merged.sort_values("trade_date").reset_index(drop=True)
    
    # 差分を計算
    df_merged["diff"] = df_merged["port_ret_cc_return"] - df_merged["port_ret_cc_weights"]
    df_merged["abs_diff"] = df_merged["diff"].abs()
    
    # 累積リターンを計算
    df_merged["cumret_return"] = (1.0 + df_merged["port_ret_cc_return"]).cumprod()
    df_merged["cumret_weights"] = (1.0 + df_merged["port_ret_cc_weights"]).cumprod()
    df_merged["cumret_diff"] = df_merged["cumret_return"] - df_merged["cumret_weights"]
    
    return df_merged


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== cross4 Returns 比較・集計 ===")
    print("=" * 80)
    
    # 既存のreturn合成cross4を読み込む
    print("\n[STEP 1] 既存のreturn合成cross4を読み込み中...")
    try:
        df_return = load_return_synthetic_cross4()
        print(f"  ✓ {len(df_return)} 日分")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # weights→returnsで生成したcross4を読み込む
    print("\n[STEP 2] weights→returnsで生成したcross4を読み込み中...")
    try:
        df_weights = load_weights_synthetic_cross4()
        print(f"  ✓ {len(df_weights)} 日分")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 統計を計算
    print("\n[STEP 3] 統計を計算中...")
    stats_return = calculate_summary_stats(df_return, "Return合成cross4")
    stats_weights = calculate_summary_stats(df_weights, "Weights→Returns cross4")
    
    # 比較用DataFrameを作成
    df_stats = pd.DataFrame([stats_return, stats_weights])
    
    # 差分を計算
    df_stats_diff = pd.DataFrame({
        "項目": ["累積リターン差分", "年率リターン差分", "年率ボラティリティ差分", "Sharpe比差分", "最大ドローダウン差分"],
        "差分": [
            stats_return["累積リターン"] - stats_weights["累積リターン"],
            stats_return["年率リターン"] - stats_weights["年率リターン"],
            stats_return["年率ボラティリティ"] - stats_weights["年率ボラティリティ"],
            stats_return["Sharpe比"] - stats_weights["Sharpe比"],
            stats_return["最大ドローダウン"] - stats_weights["最大ドローダウン"],
        ]
    })
    
    # 詳細比較
    print("\n[STEP 4] 詳細比較を計算中...")
    df_compare = compare_returns(df_return, df_weights)
    
    # 結果を表示
    print("\n" + "=" * 80)
    print("【統計比較】")
    print("=" * 80)
    
    # 数値フォーマット
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)
    
    # 統計を表示（見やすい形式で）
    for col in ["期間開始", "期間終了", "日数"]:
        if col in df_stats.columns:
            print(f"\n{col}:")
            for _, row in df_stats.iterrows():
                print(f"  {row['label']}: {row[col]}")
    
    for col in ["累積リターン", "年率リターン", "年率ボラティリティ", "Sharpe比", "最大ドローダウン", "勝率"]:
        if col in df_stats.columns:
            print(f"\n{col}:")
            for _, row in df_stats.iterrows():
                if isinstance(row[col], float):
                    if "リターン" in col or "ドローダウン" in col:
                        print(f"  {row['label']}: {row[col]:.4%}")
                    elif col == "Sharpe比":
                        print(f"  {row['label']}: {row[col]:.4f}")
                    elif col == "勝率":
                        print(f"  {row['label']}: {row[col]:.2%}")
                    else:
                        print(f"  {row['label']}: {row[col]:.6f}")
                else:
                    print(f"  {row['label']}: {row[col]}")
    
    print("\n" + "=" * 80)
    print("【差分統計】")
    print("=" * 80)
    print(df_stats_diff.to_string(index=False))
    
    # 日次差分の統計
    print("\n" + "=" * 80)
    print("【日次差分統計】")
    print("=" * 80)
    print(f"平均絶対差分: {df_compare['abs_diff'].mean():.8f}")
    print(f"最大絶対差分: {df_compare['abs_diff'].max():.8f}")
    print(f"最小絶対差分: {df_compare['abs_diff'].min():.8f}")
    print(f"標準偏差: {df_compare['abs_diff'].std():.8f}")
    print(f"累積リターン差分（最終日）: {df_compare['cumret_diff'].iloc[-1]:.8f}")
    
    # 保存
    output_stats = RESEARCH_DIR / "cross4_returns_comparison_stats.csv"
    df_stats.to_csv(output_stats, index=False, encoding='utf-8-sig')
    print(f"\n✓ 統計比較を保存: {output_stats}")
    
    output_diff = RESEARCH_DIR / "cross4_returns_comparison_diff.csv"
    df_stats_diff.to_csv(output_diff, index=False, encoding='utf-8-sig')
    print(f"✓ 差分統計を保存: {output_diff}")
    
    output_detail = RESEARCH_DIR / "cross4_returns_comparison_detail.parquet"
    df_compare.to_parquet(output_detail, index=False)
    print(f"✓ 詳細比較を保存: {output_detail}")
    
    print("\n" + "=" * 80)
    print("完了: cross4 Returns 比較・集計完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

