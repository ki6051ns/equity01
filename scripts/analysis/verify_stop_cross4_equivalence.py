#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/verify_stop_cross4_equivalence.py

STOP付cross4 weights版とeval_stop_regimes.pyとの差分検証（analysis内で完結）

入力:
- data/processed/weights_bt/cross4_from_weights_{strategy}_w{window}.parquet（weights版）
- data/processed/stop_regime_strategies.parquet（eval_stop_regimes.pyの出力）

出力:
- data/processed/research/reports/stop_cross4_equivalence_{strategy}_w{window}.csv（差分統計）
- data/processed/research/reports/stop_cross4_equivalence_detail_{strategy}_w{window}.parquet（詳細比較）

重要: この段階ではまだprdに接続しない。まずanalysis内で一致検証。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/verify_stop_cross4_equivalence.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_baseline_weights_returns() -> pd.DataFrame:
    """
    ベースライン（STOP無し）のweights版returnsを読み込む
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    path = WEIGHTS_BT_DIR / "cross4_from_weights.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"ベースラインweights版returnsファイルが見つかりません: {path}\n"
            "先に backtest_from_weights.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    return df


def load_baseline_eval_returns() -> pd.DataFrame:
    """
    ベースライン（STOP無し）のeval_stop_regimes.pyのreturnsを読み込む
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    # cross4のリターンを読み込む（STOP無し）
    cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    
    if not cross4_path.exists():
        raise FileNotFoundError(
            f"ベースラインcross4 returnsファイルが見つかりません: {cross4_path}\n"
            "先に ensemble_variant_cross4.py を実行してください。"
        )
    
    df = pd.read_parquet(cross4_path)
    
    if "trade_date" not in df.columns:
        raise KeyError(f"trade_date列が見つかりません: {df.columns.tolist()}")
    
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    if "port_ret_cc" not in df.columns:
        raise KeyError(f"port_ret_cc列が見つかりません: {df.columns.tolist()}")
    
    return df[["trade_date", "port_ret_cc"]]


def load_weights_based_returns(strategy: str, window: int = None) -> pd.DataFrame:
    """
    weights版のreturnsを読み込む
    
    Parameters
    ----------
    strategy : str
        "baseline", "stop0", "planA", "planB" のいずれか
    window : int, optional
        ウィンドウサイズ（60, 120）。baselineの場合はNone
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    if strategy == "baseline":
        return load_baseline_weights_returns()
    
    if window is None:
        raise ValueError(f"windowが指定されていません（strategy={strategy}）")
    
    path = WEIGHTS_BT_DIR / f"cross4_from_weights_{strategy}_w{window}.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"weights版returnsファイルが見つかりません: {path}\n"
            f"先に backtest_from_weights_with_stop.py --strategy {strategy} --window {window} を実行してください。"
        )
    
    df = pd.read_parquet(path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    
    return df


def load_eval_stop_regimes_returns(strategy: str, window: int = None) -> pd.DataFrame:
    """
    eval_stop_regimes.pyの出力を読み込む
    
    Parameters
    ----------
    strategy : str
        "baseline", "stop0", "planA", "planB" のいずれか
    window : int, optional
        ウィンドウサイズ（60, 120）。baselineの場合はNone
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc を含むDataFrame
    """
    if strategy == "baseline":
        return load_baseline_eval_returns()
    
    if window is None:
        raise ValueError(f"windowが指定されていません（strategy={strategy}）")
    
    path = DATA_DIR / "stop_regime_strategies.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"eval_stop_regimes.pyの出力ファイルが見つかりません: {path}\n"
            "先に eval_stop_regimes.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
    df[date_col] = pd.to_datetime(df[date_col])
    
    # リターン列を確認
    ret_col = f"{strategy}_{window}"
    if ret_col not in df.columns:
        raise KeyError(
            f"リターン列 '{ret_col}' が見つかりません。\n"
            f"利用可能な列: {[c for c in df.columns if c not in [date_col]]}"
        )
    
    return df[[date_col, ret_col]].rename(columns={date_col: "trade_date", ret_col: "port_ret_cc"})


def compare_returns(
    df_weights: pd.DataFrame,
    df_eval: pd.DataFrame,
    strategy: str,
    window: int = None
) -> dict:
    """
    2つのreturnsを比較
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        weights版のreturns
    df_eval : pd.DataFrame
        eval_stop_regimes.pyのreturns
    strategy : str
        戦略名
    window : int, optional
        ウィンドウサイズ（baselineの場合はNone）
    
    Returns
    -------
    dict
        比較結果の統計
    """
    # 日付でマージ
    df_merged = df_weights[["trade_date", "port_ret_cc"]].merge(
        df_eval[["trade_date", "port_ret_cc"]],
        on="trade_date",
        how="inner",
        suffixes=("_weights", "_eval")
    )
    
    if df_merged.empty:
        return {
            "strategy": strategy,
            "window": window,
            "status": "FAIL",
            "reason": "共通日付が見つかりません",
            "common_dates": 0,
        }
    
    # 差分を計算
    df_merged["diff"] = df_merged["port_ret_cc_weights"] - df_merged["port_ret_cc_eval"]
    df_merged["abs_diff"] = df_merged["diff"].abs()
    
    # 累積リターンの差分
    cum_weights = (1.0 + df_merged["port_ret_cc_weights"]).prod()
    cum_eval = (1.0 + df_merged["port_ret_cc_eval"]).prod()
    cum_diff = cum_weights - cum_eval
    
    # 統計
    mean_abs_diff = df_merged["abs_diff"].mean()
    max_abs_diff = df_merged["abs_diff"].max()
    std_diff = df_merged["diff"].std()
    
    # 一致判定（許容誤差: 1e-8）
    tolerance = 1e-8
    is_equal = (df_merged["abs_diff"] <= tolerance).all()
    
    # 大きな差分がある日のTop20
    top_diff_days = df_merged.nlargest(20, "abs_diff")[[
        "trade_date",
        "port_ret_cc_weights",
        "port_ret_cc_eval",
        "diff",
        "abs_diff"
    ]].copy()
    
    result = {
        "strategy": strategy,
        "window": window,
        "window_str": f"w{window}" if window is not None else "baseline",
        "status": "PASS" if is_equal else "FAIL",
        "common_dates": len(df_merged),
        "mean_abs_diff": mean_abs_diff,
        "max_abs_diff": max_abs_diff,
        "std_diff": std_diff,
        "cum_ret_weights": cum_weights - 1.0,
        "cum_ret_eval": cum_eval - 1.0,
        "cum_ret_diff": cum_diff,
        "tolerance": tolerance,
        "top_diff_days": top_diff_days,
        "detail_df": df_merged,
    }
    
    return result


def print_comparison_result(result: dict):
    """
    比較結果を表示
    
    Parameters
    ----------
    result : dict
        比較結果
    """
    print("\n" + "=" * 80)
    strategy_display = result['strategy'].upper()
    window_display = result['window_str']
    print(f"【比較結果: {strategy_display} ({window_display})】")
    print("=" * 80)
    
    print(f"\nステータス: {result['status']}")
    print(f"共通日数: {result['common_dates']} 日")
    
    if result['status'] == "FAIL":
        print(f"\n差分統計:")
        print(f"  平均絶対差分: {result['mean_abs_diff']:.8f}")
        print(f"  最大絶対差分: {result['max_abs_diff']:.8f}")
        print(f"  差分の標準偏差: {result['std_diff']:.8f}")
        print(f"  許容誤差: {result['tolerance']:.8f}")
        
        print(f"\n累積リターン:")
        print(f"  weights版: {result['cum_ret_weights']:.6f}")
        print(f"  eval版: {result['cum_ret_eval']:.6f}")
        print(f"  差分: {result['cum_ret_diff']:.8f}")
        
        # 大きな差分がある日のTop10
        print(f"\n【差分が大きい日 Top10】")
        top10 = result['top_diff_days'].head(10)
        for _, row in top10.iterrows():
            print(f"  {row['trade_date'].date()}: diff={row['diff']:.8f} "
                  f"(weights={row['port_ret_cc_weights']:.8f}, "
                  f"eval={row['port_ret_cc_eval']:.8f})")
    else:
        print("\n✓ 完全一致（許容誤差内）")


def save_comparison_result(result: dict):
    """
    比較結果を保存
    
    Parameters
    ----------
    result : dict
        比較結果
    """
    # 統計をCSVに保存
    stats_path = RESEARCH_REPORTS_DIR / f"stop_cross4_equivalence_{result['strategy']}_{result['window_str']}.csv"
    
    stats_df = pd.DataFrame([{
        "strategy": result['strategy'],
        "window": result['window_str'],
        "status": result['status'],
        "common_dates": result['common_dates'],
        "mean_abs_diff": result['mean_abs_diff'],
        "max_abs_diff": result['max_abs_diff'],
        "std_diff": result['std_diff'],
        "cum_ret_weights": result['cum_ret_weights'],
        "cum_ret_eval": result['cum_ret_eval'],
        "cum_ret_diff": result['cum_ret_diff'],
        "tolerance": result['tolerance'],
    }])
    
    stats_df.to_csv(stats_path, index=False)
    print(f"\n✓ 統計を保存: {stats_path}")
    
    # 詳細をParquetに保存
    detail_path = RESEARCH_REPORTS_DIR / f"stop_cross4_equivalence_detail_{result['strategy']}_{result['window_str']}.parquet"
    result['detail_df'].to_parquet(detail_path, index=False)
    print(f"✓ 詳細を保存: {detail_path}")


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="STOP付cross4 weights版とeval_stop_regimes.pyとの差分検証（全戦略対応）"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        choices=["baseline", "stop0", "planA", "planB"],
        help="戦略（baseline, stop0, planA, planB）。指定しない場合は全戦略を実行"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        choices=[60, 120],
        help="ウィンドウサイズ（60, 120）。指定しない場合は全windowを実行"
    )
    
    args = parser.parse_args()
    
    # 全戦略・全windowを定義
    all_strategies = ["baseline", "stop0", "planA", "planB"]
    all_windows = [60, 120]
    
    # 実行対象を決定
    if args.strategy is not None:
        strategies = [args.strategy]
    else:
        strategies = all_strategies
    
    # baselineの場合はwindowを無視
    if args.window is not None:
        windows = [args.window]
    else:
        windows = all_windows
    
    print("=" * 80)
    print("=== STOP付cross4 Equivalence検証（全戦略比較） ===")
    print("=" * 80)
    print(f"\n実行対象:")
    print(f"  戦略: {strategies}")
    if "baseline" not in strategies:
        print(f"  Windows: {windows}")
    print()
    
    all_results = []
    failed_count = 0
    
    # 各戦略・各windowで比較
    for strategy in strategies:
        # baselineの場合はwindowをスキップ
        if strategy == "baseline":
            windows_to_run = [None]
        else:
            windows_to_run = windows
        
        for window in windows_to_run:
            window_str = "baseline" if window is None else f"w{window}"
            print("\n" + "=" * 80)
            print(f"【処理中: {strategy.upper()} ({window_str})】")
            print("=" * 80)
            
            try:
                # weights版のreturnsを読み込む
                print(f"\n[STEP 1] weights版returnsを読み込み中...")
                df_weights = load_weights_based_returns(strategy, window)
                print(f"  ✓ {len(df_weights)} 日分")
                
                # eval_stop_regimes.pyのreturnsを読み込む
                print(f"\n[STEP 2] eval_stop_regimes.pyのreturnsを読み込み中...")
                df_eval = load_eval_stop_regimes_returns(strategy, window)
                print(f"  ✓ {len(df_eval)} 日分")
                
                # 比較
                print(f"\n[STEP 3] 比較中...")
                result = compare_returns(df_weights, df_eval, strategy, window)
                all_results.append(result)
                
                # 結果を表示
                print_comparison_result(result)
                
                # 保存
                print(f"\n[STEP 4] 結果を保存中...")
                save_comparison_result(result)
                
                if result['status'] == "FAIL":
                    failed_count += 1
                    
            except (FileNotFoundError, KeyError, ValueError) as e:
                print(f"  ✗ エラー: {e}")
                failed_count += 1
                continue
    
    # 全結果のサマリー
    print("\n" + "=" * 80)
    print("【全結果サマリー】")
    print("=" * 80)
    
    summary_df = pd.DataFrame([{
        "strategy": r["strategy"],
        "window": r["window_str"],
        "status": r["status"],
        "common_dates": r["common_dates"],
        "mean_abs_diff": r.get("mean_abs_diff", np.nan),
        "max_abs_diff": r.get("max_abs_diff", np.nan),
        "cum_ret_weights": r.get("cum_ret_weights", np.nan),
        "cum_ret_eval": r.get("cum_ret_eval", np.nan),
        "cum_ret_diff": r.get("cum_ret_diff", np.nan),
    } for r in all_results])
    
    print("\n比較結果一覧:")
    print(summary_df.to_string(index=False, float_format="%.6f"))
    
    # サマリーをCSVに保存
    summary_path = RESEARCH_REPORTS_DIR / "stop_cross4_equivalence_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\n✓ サマリーを保存: {summary_path}")
    
    print("\n" + "=" * 80)
    print(f"完了: STOP付cross4 Equivalence検証完了（FAIL: {failed_count}/{len(all_results)}）")
    print("=" * 80)
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

