#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/debug_single_date_reproduction.py

【2】差分日の最小再現テスト（1日限定）

特定の日付について、以下の3パターンを並べて比較：
- w[t-1] * r[t]
- w[t]   * r[t]
- w[t-1] * r[t+1]（念のため）

eval側の値と一致するものを特定してフラグを立てる。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from scripts.tools import data_loader

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"


def calculate_port_ret_for_date_pattern(
    weights_path: Path,
    target_date: pd.Timestamp,
    weight_lag: int,
    return_offset: int,
    use_adj_close: bool = True
):
    """
    特定の日付パターンでポートフォリオリターンを計算
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス
    target_date : pd.Timestamp
        対象日（t）
    weight_lag : int
        weightsのラグ（0ならw[t], -1ならw[t-1]）
    return_offset : int
        リターンのオフセット（0ならr[t], 1ならr[t+1]）
    use_adj_close : bool
        Trueならadj_close、Falseならcloseを使用
    
    Returns
    -------
    dict
        port_ret, w_used_date, ret_date, formula, contrib_df を含むdict
    """
    # weightsファイルを読み込む
    df_weights = pd.read_parquet(weights_path)
    df_weights["date"] = pd.to_datetime(df_weights["date"])
    
    # 価格データを読み込む
    df_prices_all = data_loader.load_prices()
    price_date_col = "date" if "date" in df_prices_all.columns else "trade_date"
    df_prices_all[price_date_col] = pd.to_datetime(df_prices_all[price_date_col])
    
    # 価格カラムを選択
    price_col = "adj_close" if (use_adj_close and "adj_close" in df_prices_all.columns) else "close"
    
    # 日付リストを取得
    weights_dates = sorted(df_weights["date"].unique())
    prices_dates = sorted(df_prices_all[price_date_col].unique())
    
    # w_used_dateを決定
    w_used_date = None
    if weight_lag == 0:
        # w[t]
        if target_date in weights_dates:
            w_used_date = target_date
    elif weight_lag == -1:
        # w[t-1]
        for d in reversed(weights_dates):
            if d < target_date:
                w_used_date = d
                break
    
    if w_used_date is None:
        return {
            "port_ret": np.nan,
            "w_used_date": None,
            "ret_date": None,
            "formula": f"w[t{weight_lag:+d}] * r[t{return_offset:+d}] (不可)",
            "contrib_df": pd.DataFrame()
        }
    
    # ret_dateを決定
    ret_date = None
    target_idx = None
    for i, d in enumerate(prices_dates):
        if d >= target_date:
            target_idx = i
            break
    
    if target_idx is not None:
        ret_idx = target_idx + return_offset
        if 0 <= ret_idx < len(prices_dates):
            ret_date = prices_dates[ret_idx]
    
    if ret_date is None:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": None,
            "formula": f"w[{w_used_date.date()}] * r[t{return_offset:+d}] (r不可)",
            "contrib_df": pd.DataFrame()
        }
    
    # weightsを取得
    weights_day = df_weights[df_weights["date"] == w_used_date].copy()
    if weights_day.empty:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": ret_date,
            "formula": f"w[{w_used_date.date()}] * r[{ret_date.date()}] (weights空)",
            "contrib_df": pd.DataFrame()
        }
    
    weights_series = weights_day.set_index("symbol")["weight"]
    
    # リターンを計算
    # ret_dateの前営業日を取得
    ret_date_idx = None
    for i, d in enumerate(prices_dates):
        if d >= ret_date:
            ret_date_idx = i
            break
    
    if ret_date_idx is None or ret_date_idx == 0:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": ret_date,
            "formula": f"w[{w_used_date.date()}] * r[{ret_date.date()}] (前営業日取得不可)",
            "contrib_df": pd.DataFrame()
        }
    
    prev_date_for_ret = prices_dates[ret_date_idx - 1]
    prices_prev_for_ret = df_prices_all[df_prices_all[price_date_col] == prev_date_for_ret].copy()
    prices_target = df_prices_all[df_prices_all[price_date_col] == ret_date].copy()
    
    if prices_prev_for_ret.empty or prices_target.empty:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": ret_date,
            "formula": f"w[{w_used_date.date()}] * r[{ret_date.date()}] (価格データ不足)",
            "contrib_df": pd.DataFrame()
        }
    
    # リターン計算: r[t] = price[t] / price[t-1] - 1
    prices_prev_idx = prices_prev_for_ret.set_index("symbol")[price_col]
    prices_target_idx = prices_target.set_index("symbol")[price_col]
    
    common_symbols = prices_prev_idx.index.intersection(prices_target_idx.index)
    if len(common_symbols) == 0:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": ret_date,
            "formula": f"w[{w_used_date.date()}] * r[{ret_date.date()}] (共通銘柄なし)",
            "contrib_df": pd.DataFrame()
        }
    
    rets_series = (prices_target_idx.loc[common_symbols] / prices_prev_idx.loc[common_symbols] - 1.0).fillna(0.0)
    
    # 寄与を計算
    common_symbols_final = weights_series.index.intersection(rets_series.index)
    if len(common_symbols_final) == 0:
        return {
            "port_ret": np.nan,
            "w_used_date": w_used_date,
            "ret_date": ret_date,
            "formula": f"w[{w_used_date.date()}] * r[{ret_date.date()}] (最終共通銘柄なし)",
            "contrib_df": pd.DataFrame()
        }
    
    weights_aligned = weights_series.loc[common_symbols_final].fillna(0.0)
    rets_aligned = rets_series.loc[common_symbols_final].fillna(0.0)
    
    contrib = weights_aligned * rets_aligned
    port_ret = contrib.sum()
    
    # 寄与DataFrameを作成
    contrib_df = pd.DataFrame({
        "symbol": contrib.index,
        "weight": weights_aligned.values,
        "ret": rets_aligned.values,
        "contribution": contrib.values
    }).sort_values("contribution", key=lambda x: x.abs(), ascending=False)
    
    formula_str = f"w[{w_used_date.date()}] * r[{ret_date.date()}]"
    if weight_lag == -1 and return_offset == 0:
        formula_str += " = w[t-1] * r[t]"
    elif weight_lag == 0 and return_offset == 0:
        formula_str += " = w[t] * r[t]"
    elif weight_lag == -1 and return_offset == 1:
        formula_str += " = w[t-1] * r[t+1]"
    
    return {
        "port_ret": port_ret,
        "w_used_date": w_used_date,
        "ret_date": ret_date,
        "formula": formula_str,
        "contrib_df": contrib_df
    }


def test_single_date_reproduction(
    strategy: str,
    window: int,
    target_date_str: str,
    eval_port_ret: float
):
    """
    特定日の最小再現テスト
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    target_date_str : str
        対象日（YYYY-MM-DD）
    eval_port_ret : float
        eval側のポートフォリオリターン（比較用）
    """
    target_date = pd.to_datetime(target_date_str)
    weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
    
    print("=" * 80)
    print(f"=== 単日再現テスト: {strategy.upper()} (window={window}), 対象日={target_date.date()} ===")
    print("=" * 80)
    print(f"\n  eval側のport_ret: {eval_port_ret:.10f}")
    print(f"\n  テストパターン:")
    print("    1. w[t-1] * r[t]  (標準)")
    print("    2. w[t]   * r[t]  (look-aheadの可能性)")
    print("    3. w[t-1] * r[t+1] (念のため)")
    print("\n" + "=" * 80)
    
    # 3パターンをテスト
    patterns = [
        {"weight_lag": -1, "return_offset": 0, "name": "w[t-1] * r[t]"},
        {"weight_lag": 0, "return_offset": 0, "name": "w[t] * r[t]"},
        {"weight_lag": -1, "return_offset": 1, "name": "w[t-1] * r[t+1]"},
    ]
    
    results = []
    for pattern in patterns:
        result = calculate_port_ret_for_date_pattern(
            weights_path=weights_path,
            target_date=target_date,
            weight_lag=pattern["weight_lag"],
            return_offset=pattern["return_offset"],
            use_adj_close=True
        )
        
        diff = abs(result["port_ret"] - eval_port_ret) if not pd.isna(result["port_ret"]) else np.inf
        if diff < 1e-8:
            match_flag = "[MATCH]"
        elif diff < 1e-6:
            match_flag = "[CLOSE]"
        else:
            match_flag = "[DIFF]"
        
        results.append({
            "pattern": pattern["name"],
            "port_ret": result["port_ret"],
            "diff": diff,
            "match_flag": match_flag,
            "w_used_date": result["w_used_date"],
            "ret_date": result["ret_date"],
            "formula": result["formula"],
            "contrib_df": result["contrib_df"]
        })
    
    # 結果を表示
    print("\n[結果比較]")
    print("=" * 80)
    for r in results:
        print(f"\n  パターン: {r['pattern']}")
        print(f"    式表記: {r['formula']}")
        if r['w_used_date']:
            print(f"    w_used_date: {r['w_used_date'].date()}")
        if r['ret_date']:
            print(f"    ret_date: {r['ret_date'].date()}")
        if not pd.isna(r['port_ret']):
            print(f"    port_ret: {r['port_ret']:.10f}")
            print(f"    evalとの差分: {r['diff']:.10f}")
            print(f"    判定: {r['match_flag']}")
        else:
            print(f"    port_ret: NaN (計算不可)")
    
    # 最良の一致を判定
    valid_results = [r for r in results if not pd.isna(r['port_ret'])]
    if valid_results:
        best_match = min(valid_results, key=lambda x: x['diff'])
        print(f"\n[結論]")
        print("=" * 80)
        print(f"  最良の一致: {best_match['pattern']}")
        print(f"  式表記: {best_match['formula']}")
        print(f"  port_ret: {best_match['port_ret']:.10f}")
        print(f"  evalとの差分: {best_match['diff']:.10f}")
        print(f"  判定: {best_match['match_flag']}")
        
        if best_match['diff'] < 1e-8:
            print(f"\n  → eval側は「{best_match['pattern']}」のロジックを使用していると確定")
        elif best_match['diff'] < 1e-6:
            print(f"\n  → eval側は「{best_match['pattern']}」に近いロジックを使用している可能性が高い")
        else:
            print(f"\n  → eval側は上記パターンのいずれとも一致しない（他の要因あり）")


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="特定日の最小再現テスト（w[t-1]*r[t] vs w[t]*r[t] vs w[t-1]*r[t+1]）"
    )
    parser.add_argument("--strategy", type=str, required=True, choices=["stop0", "planA", "planB"], help="戦略")
    parser.add_argument("--window", type=int, required=True, choices=[60, 120], help="ウィンドウサイズ")
    parser.add_argument("--date", type=str, required=True, help="対象日（YYYY-MM-DD）")
    
    args = parser.parse_args()
    
    # eval側のport_retを取得
    eval_path = DATA_DIR / "stop_regime_strategies.parquet"
    if not eval_path.exists():
        print(f"[ERROR] eval側の結果ファイルが見つかりません: {eval_path}")
        return
    
    df_eval = pd.read_parquet(eval_path)
    date_col = "trade_date" if "trade_date" in df_eval.columns else "date"
    df_eval[date_col] = pd.to_datetime(df_eval[date_col])
    
    strategy_col = f"{args.strategy}_{args.window}"
    if strategy_col not in df_eval.columns:
        print(f"[ERROR] 戦略カラム '{strategy_col}' が見つかりません")
        return
    
    target_date = pd.to_datetime(args.date)
    eval_row = df_eval[df_eval[date_col] == target_date]
    
    if len(eval_row) == 0:
        print(f"[ERROR] 対象日 {args.date} がeval側の結果に存在しません")
        return
    
    eval_port_ret = eval_row[strategy_col].iloc[0]
    
    if pd.isna(eval_port_ret):
        print(f"[ERROR] 対象日 {args.date} のeval側のport_retがNaNです")
        return
    
    # テスト実行
    test_single_date_reproduction(
        strategy=args.strategy,
        window=args.window,
        target_date_str=args.date,
        eval_port_ret=eval_port_ret
    )


if __name__ == "__main__":
    main()

