#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/compare_eval_vs_weights_stop.py

eval_stop_regimes.py と backtest_from_weights_with_stop.py の結果を比較

目的:
- eval_stop_regimes.pyの結果（再構築されたport_retを使用）と
- backtest_from_weights_with_stop.pyの結果（weightsから計算されたreturns）
を比較し、一致度を検証する
"""

import sys
import io
import os
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32':
    # 環境変数を設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 標準出力のエンコーディングをUTF-8に設定
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.7以前の互換性
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # 既に設定されている場合はスキップ
        pass

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_eval_results(strategy: str, window: int) -> pd.DataFrame:
    """
    eval_stop_regimes.pyの結果を読み込む
    
    Parameters
    ----------
    strategy : str
        "baseline", "stop0", "planA", "planB"
    window : int
        60 or 120
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    eval_path = DATA_DIR / "stop_regime_strategies.parquet"
    
    if not eval_path.exists():
        raise FileNotFoundError(
            f"eval_stop_regimes.pyの出力ファイルが見つかりません: {eval_path}\n"
            "先に eval_stop_regimes.py を実行してください。"
        )
    
    df = pd.read_parquet(eval_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
    df[date_col] = pd.to_datetime(df[date_col])
    
    # 戦略カラムを特定
    if strategy == "baseline":
        strategy_col = "baseline"
    else:
        strategy_col = f"{strategy}_{window}"
    
    if strategy_col not in df.columns:
        raise KeyError(f"戦略カラム '{strategy_col}' が見つかりません。利用可能な列: {df.columns.tolist()}")
    
    # 結果をDataFrameにまとめる
    result_df = pd.DataFrame({
        "trade_date": df[date_col],
        "port_ret_cc": df[strategy_col],
    })
    
    result_df = result_df.dropna().sort_values("trade_date").reset_index(drop=True)
    
    return result_df


def load_weights_results(strategy: str, window: int) -> pd.DataFrame:
    """
    backtest_from_weights_with_stop.pyの結果を読み込む
    
    Parameters
    ----------
    strategy : str
        "stop0", "planA", "planB"
    window : int
        60 or 120
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    weights_path = WEIGHTS_BT_DIR / f"cross4_from_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        raise FileNotFoundError(
            f"backtest_from_weights_with_stop.pyの出力ファイルが見つかりません: {weights_path}\n"
            f"先に backtest_from_weights_with_stop.py --strategy {strategy} --window {window} を実行してください。"
        )
    
    df = pd.read_parquet(weights_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
    df[date_col] = pd.to_datetime(df[date_col])
    
    if "port_ret_cc" not in df.columns:
        raise KeyError(f"port_ret_cc列が見つかりません: {df.columns.tolist()}")
    
    # 結果をDataFrameにまとめる
    result_df = pd.DataFrame({
        "trade_date": df[date_col],
        "port_ret_cc": df["port_ret_cc"],
    })
    
    result_df = result_df.dropna().sort_values("trade_date").reset_index(drop=True)
    
    return result_df


def compare_results(
    eval_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    strategy: str,
    window: int,
    tolerance: float = 1e-8
) -> dict:
    """
    2つの結果を比較する
    
    Parameters
    ----------
    eval_df : pd.DataFrame
        eval_stop_regimes.pyの結果
    weights_df : pd.DataFrame
        backtest_from_weights_with_stop.pyの結果
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    tolerance : float
        許容誤差（デフォルト: 1e-8）
    
    Returns
    -------
    dict
        比較結果を含む辞書
    """
    # 日付でマージ
    merged = pd.merge(
        eval_df,
        weights_df,
        on="trade_date",
        how="inner",
        suffixes=("_eval", "_weights")
    )
    
    if len(merged) == 0:
        return {
            "strategy": strategy,
            "window": window,
            "status": "FAIL",
            "reason": "共通日付が存在しません",
            "common_dates": 0,
        }
    
    # 差分を計算
    merged["diff"] = merged["port_ret_cc_eval"] - merged["port_ret_cc_weights"]
    merged["abs_diff"] = merged["diff"].abs()
    
    # 統計
    mean_abs_diff = merged["abs_diff"].mean()
    max_abs_diff = merged["abs_diff"].max()
    
    # 累積リターンの差
    cum_eval = (1 + merged["port_ret_cc_eval"]).prod() - 1
    cum_weights = (1 + merged["port_ret_cc_weights"]).prod() - 1
    cum_diff = cum_eval - cum_weights
    
    # PASS/FAIL判定
    status = "PASS" if max_abs_diff < tolerance else "FAIL"
    
    result = {
        "strategy": strategy,
        "window": window,
        "status": status,
        "common_dates": len(merged),
        "mean_abs_diff": mean_abs_diff,
        "max_abs_diff": max_abs_diff,
        "cum_ret_eval": cum_eval,
        "cum_ret_weights": cum_weights,
        "cum_ret_diff": cum_diff,
        "df_comparison": merged,
    }
    
    return result


def print_comparison_summary(result: dict):
    """
    比較結果を表示する
    """
    print(f"\n=== {result['strategy'].upper()} (window={result['window']}) ===")
    print(f"Status: {result['status']}")
    print(f"共通日数: {result['common_dates']} 日")
    print(f"平均絶対差分: {result['mean_abs_diff']:.10f}")
    print(f"最大絶対差分: {result['max_abs_diff']:.10f}")
    print(f"累積リターン (eval): {result['cum_ret_eval']*100:.4f}%")
    print(f"累積リターン (weights): {result['cum_ret_weights']*100:.4f}%")
    print(f"累積リターン差分: {result['cum_ret_diff']*100:.4f}%")
    
    if result['status'] == "FAIL":
        # 差分が大きい日Top10を表示
        df_comp = result['df_comparison']
        top_diff = df_comp.nlargest(10, "abs_diff")[["trade_date", "port_ret_cc_eval", "port_ret_cc_weights", "abs_diff"]]
        print(f"\n差分が大きい日 Top10:")
        print(top_diff.to_string(index=False, float_format="%.8f"))


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="eval_stop_regimes.py と backtest_from_weights_with_stop.py の結果を比較"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=False,
        choices=["baseline", "stop0", "planA", "planB", "all"],
        default="all",
        help="戦略（baseline, stop0, planA, planB, all）。デフォルト: all（全戦略を実行）"
    )
    parser.add_argument(
        "--window",
        type=int,
        required=False,
        choices=[60, 120],
        default=None,
        help="ウィンドウサイズ（60, 120）。baselineの場合は不要。--strategy=allの場合は無視される"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-8,
        help="許容誤差（デフォルト: 1e-8）"
    )
    
    args = parser.parse_args()
    
    # 全量実行モード
    if args.strategy == "all":
        strategies = ["stop0", "planA", "planB"]
        windows = [60, 120]
        
        print("=" * 80)
        print(f"=== eval_stop_regimes vs backtest_from_weights_with_stop 比較（全量実行） ===")
        print(f"戦略: {strategies}, ウィンドウ: {windows}")
        print("=" * 80)
        
        all_results = []
        for strategy in strategies:
            for window in windows:
                print(f"\n{'='*80}")
                print(f"戦略: {strategy.upper()}, ウィンドウ: {window}")
                print(f"{'='*80}")
                
                try:
                    result = run_comparison(strategy, window, args.tolerance)
                    all_results.append(result)
                except Exception as e:
                    print(f"[ERROR] {strategy} w{window} の比較でエラー: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        # 全結果のサマリーを表示
        print("\n" + "=" * 80)
        print("=== 全結果サマリー ===")
        print("=" * 80)
        if all_results:
            for result in all_results:
                print_comparison_summary(result)
        
        return 0
    
    # 単一戦略モード（従来通り）
    if args.strategy == "baseline":
        window = 60  # ダミー値（実際には使用されない）
    else:
        if args.window is None:
            parser.error(f"--window は {args.strategy} の場合必須です")
        window = args.window
    
    return run_comparison(args.strategy, window, args.tolerance)


def run_comparison(strategy: str, window: int, tolerance: float = 1e-8) -> dict:
    """
    単一戦略・単一ウィンドウの比較を実行
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    tolerance : float
        許容誤差
    
    Returns
    -------
    dict
        比較結果の辞書
    """
    
    # eval結果を読み込む
    print(f"\n[STEP 1] eval_stop_regimes.pyの結果を読み込み中...")
    try:
        eval_df = load_eval_results(strategy, window)
        print(f"  [OK] {len(eval_df)} 日分")
        print(f"  期間: {eval_df['trade_date'].min().date()} ～ {eval_df['trade_date'].max().date()}")
    except Exception as e:
        print(f"  [ERROR] {e}")
        raise
    
    # weights結果を読み込む（baselineの場合はスキップ）
    if strategy == "baseline":
        print(f"\n[INFO] baselineはweights版が存在しないため、比較をスキップします。")
        return None
    
    print(f"\n[STEP 2] backtest_from_weights_with_stop.pyの結果を読み込み中...")
    try:
        weights_df = load_weights_results(strategy, window)
        print(f"  [OK] {len(weights_df)} 日分")
        print(f"  期間: {weights_df['trade_date'].min().date()} ～ {weights_df['trade_date'].max().date()}")
    except Exception as e:
        print(f"  [ERROR] {e}")
        raise
    
    # 比較
    print(f"\n[STEP 3] 結果を比較中...")
    result = compare_results(eval_df, weights_df, strategy, window, tolerance=tolerance)
    
    # 結果を表示
    print_comparison_summary(result)
    
    # 詳細を保存
    output_path = RESEARCH_REPORTS_DIR / f"eval_vs_weights_comparison_{strategy}_w{window}.parquet"
    result["df_comparison"].to_parquet(output_path, index=False)
    print(f"\n[INFO] 詳細比較結果を保存: {output_path}")
    
    # サマリーをCSVに保存
    summary_path = RESEARCH_REPORTS_DIR / "eval_vs_weights_comparison_summary.csv"
    summary_row = {
        "strategy": result["strategy"],
        "window": result["window"],
        "status": result["status"],
        "common_dates": result["common_dates"],
        "mean_abs_diff": result["mean_abs_diff"],
        "max_abs_diff": result["max_abs_diff"],
        "cum_ret_eval": result["cum_ret_eval"],
        "cum_ret_weights": result["cum_ret_weights"],
        "cum_ret_diff": result["cum_ret_diff"],
    }
    
    # 既存のサマリーCSVがあれば読み込んで追記、なければ新規作成
    if summary_path.exists():
        summary_df = pd.read_csv(summary_path)
        # 同じstrategy/windowの行があれば更新、なければ追加
        mask = (summary_df["strategy"] == result["strategy"]) & (summary_df["window"] == result["window"])
        if mask.any():
            # 既存の行を削除
            summary_df = summary_df[~mask].copy()
            # 新しい行を追加
            summary_df = pd.concat([summary_df, pd.DataFrame([summary_row])], ignore_index=True)
        else:
            summary_df = pd.concat([summary_df, pd.DataFrame([summary_row])], ignore_index=True)
    else:
        summary_df = pd.DataFrame([summary_row])
    
    summary_df.to_csv(summary_path, index=False)
    print(f"[INFO] サマリーを保存: {summary_path}")
    
    return result


if __name__ == "__main__":
    sys.exit(main())

