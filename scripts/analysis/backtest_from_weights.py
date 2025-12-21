#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/backtest_from_weights.py

weightsからreturnsを計算するバックテスト（analysis内で完結、coreへ書き戻し禁止）

入力:
- cross4_target_weights.parquet（date, symbol, weight）
- 価格データ（またはリターン）

出力:
- data/processed/weights_bt/cross4_from_weights.parquet（trade_date, port_ret_cc, cumulativeなど）

重要: この段階ではまだprdに接続しない。まずanalysis内で一致検証。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/backtest_from_weights.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from scripts.tools import data_loader

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
WEIGHTS_BT_DIR.mkdir(parents=True, exist_ok=True)


def load_weights(weights_path: Path) -> pd.DataFrame:
    """
    weightsファイルを読み込む
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    if not weights_path.exists():
        raise FileNotFoundError(f"weightsファイルが見つかりません: {weights_path}")
    
    df = pd.read_parquet(weights_path)
    
    # 必須カラムを確認
    required_cols = ["date", "symbol", "weight"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"必須カラムが不足しています: {missing_cols}")
    
    # dateをdatetimeに変換
    df["date"] = pd.to_datetime(df["date"])
    
    return df


def calculate_returns_from_weights(
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame = None
) -> pd.DataFrame:
    """
    weightsからreturnsを計算する
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame
    prices_df : pd.DataFrame, optional
        価格データ（指定しない場合はdata_loaderから読み込む）
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc, cumulative を含むDataFrame
    """
    # 価格データを読み込む
    if prices_df is None:
        prices_df = data_loader.load_prices()
    
    # 価格データの日付をdatetimeに変換
    if "date" in prices_df.columns:
        prices_df["date"] = pd.to_datetime(prices_df["date"])
    
    # リターンを計算
    if "symbol" in prices_df.columns:
        prices_df = prices_df.sort_values(["symbol", "date"])
        prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
    else:
        prices_df["ret_1d"] = prices_df["close"].pct_change()
    
    # weightsの日付をソート
    df_weights = df_weights.sort_values(["date", "symbol"])
    
    # 日付ごとにリターンを計算
    # 注意: weightsファイルには全営業日が含まれている前提（ラダーで維持する日も含む）
    rows = []
    dates = sorted(df_weights["date"].unique())
    
    cumulative = 1.0
    
    for i, date in enumerate(dates):
        # 当日のweights
        weights_day = df_weights[df_weights["date"] == date].copy()
        
        if weights_day.empty:
            continue
        
        # 当日のweightsをSeriesに変換（symbolをindexに）
        weights_series = weights_day.set_index("symbol")["weight"]
        
        # 翌日のリターンを取得（weightsファイルの次の日付、または実際の次の営業日）
        # 注意: weightsファイルに全営業日が含まれている前提で、dates[i+1]を使用
        if i + 1 >= len(dates):
            break
        
        next_date = dates[i + 1]
        
        # 翌日の価格データを取得
        if "symbol" in prices_df.columns:
            prices_next = prices_df[prices_df["date"] == next_date].copy()
            if prices_next.empty:
                continue
            
            # symbolをindexに
            prices_next = prices_next.set_index("symbol")
        else:
            prices_next = prices_df[prices_df["date"] == next_date].copy()
            if prices_next.empty:
                continue
            prices_next = prices_next.set_index(prices_next.index)
        
        # 共通のsymbolを取得
        common_symbols = weights_series.index.intersection(prices_next.index)
        if len(common_symbols) == 0:
            # weightsにないsymbolはスキップ
            continue
        
        # 共通symbolのweightsとreturnsを取得
        weights_aligned = weights_series[common_symbols]
        rets_aligned = prices_next.loc[common_symbols, "ret_1d"]
        
        # NaNを0に置換
        weights_aligned = weights_aligned.fillna(0.0)
        rets_aligned = rets_aligned.fillna(0.0)
        
        # ポートフォリオリターンを計算
        port_ret_cc = float((weights_aligned * rets_aligned).sum())
        
        # 累積を更新
        cumulative *= (1.0 + port_ret_cc)
        
        rows.append({
            "trade_date": next_date,
            "port_ret_cc": port_ret_cc,
            "cumulative": cumulative,
        })
    
    df_result = pd.DataFrame(rows)
    
    if df_result.empty:
        return pd.DataFrame(columns=["trade_date", "port_ret_cc", "cumulative"])
    
    # TOPIXデータを読み込んで相対αを計算
    tpx_path = DATA_DIR / "index_tpx_daily.parquet"
    if tpx_path.exists():
        df_tpx = pd.read_parquet(tpx_path)
        if "trade_date" in df_tpx.columns:
            df_tpx["trade_date"] = pd.to_datetime(df_tpx["trade_date"])
            df_result = df_result.merge(
                df_tpx[["trade_date", "tpx_ret_cc"]],
                on="trade_date",
                how="left"
            )
            df_result["tpx_ret_cc"] = df_result["tpx_ret_cc"].ffill().bfill().fillna(0.0)
            df_result["rel_alpha_daily"] = df_result["port_ret_cc"] - df_result["tpx_ret_cc"]
        else:
            df_result["tpx_ret_cc"] = 0.0
            df_result["rel_alpha_daily"] = df_result["port_ret_cc"]
    else:
        df_result["tpx_ret_cc"] = 0.0
        df_result["rel_alpha_daily"] = df_result["port_ret_cc"]
    
    return df_result.sort_values("trade_date").reset_index(drop=True)


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="weightsからreturnsを計算するバックテスト"
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=str(WEIGHTS_DIR / "cross4_target_weights.parquet"),
        help="weightsファイルのパス"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(WEIGHTS_BT_DIR / "cross4_from_weights.parquet"),
        help="出力ファイルのパス"
    )
    
    args = parser.parse_args()
    
    weights_path = Path(args.weights)
    output_path = Path(args.output)
    
    print("=" * 80)
    print("=== WeightsからReturns計算（weights版cross4） ===")
    print("=" * 80)
    print(f"\n入力: {weights_path}")
    print(f"出力: {output_path}")
    
    # weightsを読み込む
    print("\n[STEP 1] weightsを読み込み中...")
    df_weights = load_weights(weights_path)
    print(f"  ✓ {len(df_weights)} rows")
    print(f"  日付範囲: {df_weights['date'].min()} ～ {df_weights['date'].max()}")
    
    # returnsを計算
    print("\n[STEP 2] returnsを計算中...")
    df_result = calculate_returns_from_weights(df_weights)
    
    if df_result.empty:
        print("\n[ERROR] returnsの計算に失敗しました。")
        return
    
    print(f"  ✓ {len(df_result)} 日分のリターンを計算")
    
    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_parquet(output_path, index=False)
    print(f"\n✓ 結果を保存: {output_path}")
    
    # サマリ表示
    if len(df_result) > 0:
        print("\n[サマリ]")
        print(f"  期間: {df_result['trade_date'].min()} ～ {df_result['trade_date'].max()}")
        print(f"  最終累積: {df_result['cumulative'].iloc[-1]:.4f}")
        if "rel_alpha_daily" in df_result.columns:
            print(f"  平均相対α: {df_result['rel_alpha_daily'].mean():.6f}")
            print(f"  累積相対α: {(df_result['rel_alpha_daily'] + 1).prod() - 1:.4f}")
    
    print("\n" + "=" * 80)
    print("完了: weights→returns計算完了")
    print("=" * 80)


if __name__ == "__main__":
    main()

