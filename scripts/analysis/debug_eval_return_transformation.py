#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/debug_eval_return_transformation.py

eval_stop_regimes.py でreturnがどのように変換されているかを特定

目的：
- weights版とeval版の差分が大きい日について、eval側のreturnがどのような変換
  （shift、rolling_sum等）を経ているかを機械的に判定
- 「eval_stop_regimes.py の ○行目の ○処理が returnを○日分集約し、○日ズレで適用している」
  と1文で言える状態にする
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from typing import Tuple

DATA_DIR = Path("data/processed")
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_eval_returns_raw() -> pd.Series:
    """
    eval_stop_regimes.pyが使用するcross4 returnの元Seriesを読み込む
    
    Returns
    -------
    pd.Series
        trade_dateをindexとする日次リターン
    """
    cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    
    if not cross4_path.exists():
        raise FileNotFoundError(f"cross4 returnsファイルが見つかりません: {cross4_path}")
    
    df = pd.read_parquet(cross4_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["trade_date", "date"]:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    
    # リターンカラムを確認
    port_col = None
    for col in ["port_ret_cc", "port_ret_cc_ens", "combined_ret"]:
        if col in df.columns:
            port_col = col
            break
    
    if port_col is None:
        raise KeyError(f"リターンカラムが見つかりません: {df.columns.tolist()}")
    
    port_ret = df[port_col].dropna()
    
    return port_ret


def create_return_transformations(port_ret: pd.Series) -> pd.DataFrame:
    """
    returnの各種変換を計算してDataFrameにまとめる
    
    Parameters
    ----------
    port_ret : pd.Series
        元のreturn Series
    
    Returns
    -------
    pd.DataFrame
        date, ret_raw, shift(-2), shift(-1), shift(1), shift(2),
        rolling_sum(2), rolling_sum(3), rolling_sum(60), rolling_sum(120),
        rolling_sum(2).shift(1), rolling_sum(3).shift(1) 等を含む
    """
    df = pd.DataFrame(index=port_ret.index)
    df["date"] = df.index
    df["ret_raw"] = port_ret.values
    
    # shift変換
    df["ret_shift_m2"] = port_ret.shift(-2).values  # t-2日のreturn
    df["ret_shift_m1"] = port_ret.shift(-1).values  # t-1日のreturn
    df["ret_shift_p1"] = port_ret.shift(1).values   # t+1日のreturn
    df["ret_shift_p2"] = port_ret.shift(2).values   # t+2日のreturn
    
    # rolling_sum変換（shift無し）
    df["ret_rolling_sum_2"] = port_ret.rolling(window=2, min_periods=1).sum().values
    df["ret_rolling_sum_3"] = port_ret.rolling(window=3, min_periods=1).sum().values
    df["ret_rolling_sum_60"] = port_ret.rolling(window=60, min_periods=1).sum().values
    df["ret_rolling_sum_120"] = port_ret.rolling(window=120, min_periods=1).sum().values
    
    # rolling_sum + shift変換
    df["ret_rolling_sum_2_shift_p1"] = port_ret.rolling(window=2, min_periods=1).sum().shift(1).values
    df["ret_rolling_sum_3_shift_p1"] = port_ret.rolling(window=3, min_periods=1).sum().shift(1).values
    df["ret_rolling_sum_60_shift_p1"] = port_ret.rolling(window=60, min_periods=1).sum().shift(1).values
    df["ret_rolling_sum_120_shift_p1"] = port_ret.rolling(window=120, min_periods=1).sum().shift(1).values
    
    df["ret_rolling_sum_2_shift_m1"] = port_ret.rolling(window=2, min_periods=1).sum().shift(-1).values
    df["ret_rolling_sum_3_shift_m1"] = port_ret.rolling(window=3, min_periods=1).sum().shift(-1).values
    
    # 複合変換（2日分合算の可能性）
    # ret[t] = ret[t] + ret[t-1] に相当
    df["ret_self_plus_shift_p1"] = (port_ret + port_ret.shift(1)).values
    df["ret_self_plus_shift_m1"] = (port_ret + port_ret.shift(-1)).values
    
    # 複利変換（2日分の複利）
    # ret[t] = (1 + ret[t-1]) * (1 + ret[t]) - 1
    df["ret_compound_shift_p1"] = ((1 + port_ret.shift(1).fillna(0)) * (1 + port_ret) - 1).values
    
    return df


def load_weights_returns(strategy: str, window: int = None) -> pd.Series:
    """
    weights版のreturnsを読み込む
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int, optional
        ウィンドウサイズ
    
    Returns
    -------
    pd.Series
        trade_dateをindexとする日次リターン
    """
    if strategy == "baseline":
        weights_path = WEIGHTS_BT_DIR / "cross4_from_weights.parquet"
    else:
        weights_path = WEIGHTS_BT_DIR / f"cross4_from_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        raise FileNotFoundError(f"weights版returnsファイルが見つかりません: {weights_path}")
    
    df = pd.read_parquet(weights_path)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    
    if "port_ret_cc" not in df.columns:
        raise KeyError(f"port_ret_cc列が見つかりません: {df.columns.tolist()}")
    
    return df["port_ret_cc"]


def load_eval_strategy_returns(strategy: str, window: int = None) -> pd.Series:
    """
    eval_stop_regimes.pyの出力（stop_regime_strategies.parquet）から戦略returnを読み込む
    
    Parameters
    ----------
    strategy : str
        戦略名（"baseline", "stop0", "planA", "planB"）
    window : int, optional
        ウィンドウサイズ（baselineの場合はNone）
    
    Returns
    -------
    pd.Series
        trade_dateをindexとする日次リターン
    """
    if strategy == "baseline":
        # baselineはhorizon_ensemble_variant_cross4.parquetから
        return load_eval_returns_raw()
    
    eval_path = DATA_DIR / "stop_regime_strategies.parquet"
    if not eval_path.exists():
        raise FileNotFoundError(f"eval_stop_regimes.pyの出力ファイルが見つかりません: {eval_path}")
    
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
    df = df.set_index(date_col).sort_index()
    
    # リターン列を確認
    ret_col = f"{strategy}_{window}"
    if ret_col not in df.columns:
        raise KeyError(f"リターン列 '{ret_col}' が見つかりません")
    
    return df[ret_col]


def find_matching_transformation(
    weights_ret: pd.Series,
    eval_ret: pd.Series,
    transformations_df: pd.DataFrame,
    target_date: pd.Timestamp = None,
    tolerance: float = 1e-8
) -> dict:
    """
    weights版returnとeval版returnを比較し、どの変換が一致するかを判定
    
    Parameters
    ----------
    weights_ret : pd.Series
        weights版のreturn
    eval_ret : pd.Series
        eval版のreturn
    transformations_df : pd.DataFrame
        各種変換を含むDataFrame
    target_date : pd.Timestamp, optional
        特定の日を対象にする場合
    tolerance : float
        一致判定の許容誤差
    
    Returns
    -------
    dict
        一致した変換の情報
    """
    # 日付でマージ
    common_dates = weights_ret.index.intersection(eval_ret.index)
    if target_date is not None:
        target_date_pd = pd.to_datetime(target_date).normalize()
        if target_date_pd in common_dates:
            common_dates = [target_date_pd]
        else:
            return {"match": False, "reason": f"対象日 {target_date_pd.date()} が共通日付に存在しません"}
    
    df_comparison = pd.DataFrame({
        "date": common_dates,
        "weights_ret": weights_ret.loc[common_dates].values,
        "eval_ret": eval_ret.loc[common_dates].values,
    })
    
    # transformations_dfとマージ
    df_comparison = df_comparison.merge(
        transformations_df.reset_index()[["date"] + [col for col in transformations_df.columns if col != "date"]],
        on="date",
        how="left"
    )
    
    # 各変換列とeval_retを比較
    transformation_cols = [col for col in transformations_df.columns if col != "date" and col.startswith("ret_")]
    
    matches = []
    for col in transformation_cols:
        if col not in df_comparison.columns:
            continue
        
        # NaNを除外して比較
        mask = df_comparison[col].notna() & df_comparison["eval_ret"].notna()
        if mask.sum() == 0:
            continue
        
        diff = (df_comparison.loc[mask, "eval_ret"] - df_comparison.loc[mask, col]).abs()
        match_count = (diff <= tolerance).sum()
        match_ratio = match_count / mask.sum()
        mean_diff = diff.mean()
        max_diff = diff.max()
        
        matches.append({
            "transformation": col,
            "match_count": match_count,
            "match_ratio": match_ratio,
            "mean_diff": mean_diff,
            "max_diff": max_diff,
            "total_compared": mask.sum(),
        })
    
    # 一致度の高い順にソート
    matches = sorted(matches, key=lambda x: (x["match_ratio"], -x["mean_diff"]), reverse=True)
    
    # 完全一致（match_ratio == 1.0）を探す
    perfect_matches = [m for m in matches if m["match_ratio"] == 1.0]
    
    if perfect_matches:
        best_match = perfect_matches[0]
        return {
            "match": True,
            "transformation": best_match["transformation"],
            "match_ratio": best_match["match_ratio"],
            "mean_diff": best_match["mean_diff"],
            "max_diff": best_match["max_diff"],
            "all_matches": matches[:10],  # Top 10
        }
    else:
        # 完全一致がない場合、最も近いものを返す
        if matches:
            best_match = matches[0]
            return {
                "match": False,
                "transformation": best_match["transformation"],
                "match_ratio": best_match["match_ratio"],
                "mean_diff": best_match["mean_diff"],
                "max_diff": best_match["max_diff"],
                "all_matches": matches[:10],
            }
        else:
            return {
                "match": False,
                "reason": "一致する変換が見つかりませんでした",
            }


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="eval_stop_regimes.pyでreturnがどのように変換されているかを特定"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=["baseline", "stop0", "planA", "planB"],
        help="戦略（baseline, stop0, planA, planB）"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        choices=[60, 120],
        help="ウィンドウサイズ（60, 120）。baselineの場合は不要"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="特定の日を対象にする場合（YYYY-MM-DD形式）。指定しない場合は全期間を比較"
    )
    
    args = parser.parse_args()
    
    if args.strategy != "baseline" and args.window is None:
        parser.error("--window は baseline以外では必須です")
    
    print("=" * 80)
    print(f"=== eval_stop_regimes.py Return変換特定 ===")
    print("=" * 80)
    
    # window_strを定義
    if args.window is not None:
        window_str = f"w{args.window}"
        print(f"\n戦略: {args.strategy}")
        print(f"Window: {args.window}")
    else:
        window_str = "baseline"
        print(f"\n戦略: {args.strategy}")
    if args.date is not None:
        print(f"対象日: {args.date}")
    
    # eval版の元returnを読み込む
    print(f"\n[STEP 1] eval版の元returnを読み込み中...")
    try:
        eval_ret_raw = load_eval_returns_raw()
        print(f"  ✓ {len(eval_ret_raw)} 日分")
        print(f"  期間: {eval_ret_raw.index.min().date()} ～ {eval_ret_raw.index.max().date()}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 各種変換を計算
    print(f"\n[STEP 2] returnの各種変換を計算中...")
    transformations_df = create_return_transformations(eval_ret_raw)
    print(f"  ✓ {len(transformations_df)} 日分、{len([c for c in transformations_df.columns if c.startswith('ret_')])} 種類の変換")
    
    # eval版の戦略returnを読み込む
    print(f"\n[STEP 3] eval版の戦略returnを読み込み中...")
    try:
        eval_ret_strategy = load_eval_strategy_returns(args.strategy, args.window)
        print(f"  ✓ {len(eval_ret_strategy)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # weights版のreturnを読み込む
    print(f"\n[STEP 4] weights版のreturnを読み込み中...")
    try:
        weights_ret = load_weights_returns(args.strategy, args.window)
        print(f"  ✓ {len(weights_ret)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 変換の一致を判定
    print(f"\n[STEP 5] 変換の一致を判定中...")
    target_date = pd.to_datetime(args.date) if args.date else None
    result = find_matching_transformation(
        weights_ret,
        eval_ret_strategy,
        transformations_df,
        target_date=target_date
    )
    
    # 結果を表示
    print("\n" + "=" * 80)
    print("【判定結果】")
    print("=" * 80)
    
    if result.get("match"):
        print(f"✓ 完全一致: {result['transformation']}")
        print(f"  一致率: {result['match_ratio']:.2%}")
        print(f"  平均差分: {result['mean_diff']:.10f}")
        print(f"  最大差分: {result['max_diff']:.10f}")
        
        # 変換の説明を生成
        trans = result['transformation']
        explanation = f"eval_return[t] == {trans}"
        if "shift_m2" in trans:
            explanation += " (raw_return[t-2])"
        elif "shift_m1" in trans:
            explanation += " (raw_return[t-1])"
        elif "shift_p1" in trans:
            explanation += " (raw_return[t+1])"
        elif "shift_p2" in trans:
            explanation += " (raw_return[t+2])"
        elif "rolling_sum" in trans:
            if "shift_p1" in trans:
                explanation += " (rolling_sum + 1日遅れ)"
            elif "shift_m1" in trans:
                explanation += " (rolling_sum + 1日先行)"
            else:
                explanation += " (rolling_sum)"
        
        print(f"\n【結論】")
        print(f"{explanation}")
    else:
        print(f"✗ 完全一致なし")
        if "reason" in result:
            print(f"  理由: {result['reason']}")
        else:
            print(f"  最も近い変換: {result.get('transformation', 'N/A')}")
            print(f"  一致率: {result.get('match_ratio', 0):.2%}")
            print(f"  平均差分: {result.get('mean_diff', np.nan):.10f}")
            print(f"  最大差分: {result.get('max_diff', np.nan):.10f}")
        
        if "all_matches" in result:
            print(f"\n【Top 10 一致候補】")
            for i, match in enumerate(result["all_matches"][:10], 1):
                print(f"  {i}. {match['transformation']}: 一致率={match['match_ratio']:.2%}, 平均差分={match['mean_diff']:.10f}")
    
    # 詳細をCSVに保存
    if target_date is not None:
        output_path = RESEARCH_REPORTS_DIR / f"eval_return_transformation_{args.strategy}_{window_str}_{target_date.strftime('%Y%m%d')}.csv"
    else:
        output_path = RESEARCH_REPORTS_DIR / f"eval_return_transformation_{args.strategy}_{window_str}_all.csv"
    
    # 比較結果を保存
    common_dates = weights_ret.index.intersection(eval_ret_strategy.index)
    df_detail = pd.DataFrame({
        "date": common_dates,
        "weights_ret": weights_ret.loc[common_dates].values,
        "eval_ret": eval_ret_strategy.loc[common_dates].values,
        "diff": (eval_ret_strategy.loc[common_dates] - weights_ret.loc[common_dates]).values,
        "abs_diff": (eval_ret_strategy.loc[common_dates] - weights_ret.loc[common_dates]).abs().values,
    })
    
    # transformations_dfとマージ
    df_detail = df_detail.merge(
        transformations_df.reset_index()[["date"] + [col for col in transformations_df.columns if col != "date"]],
        on="date",
        how="left"
    )
    
    df_detail.to_csv(output_path, index=False)
    print(f"\n✓ 詳細を保存: {output_path}")
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

