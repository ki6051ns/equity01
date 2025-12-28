#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/verify_port_ret_cc_raw.py

horizon_ensemble_variant_cross4.parquet の port_ret_cc が
本当に ret_raw[t]（生の日次リターン）であるかを検証

検証1: port_ret_cc が priceからの生CC（adj_close.pct_change()）と一致するか
検証2: port_ret_cc が w×r から作られている場合、w[t] か w[t-1] かを特定
検証3: 「2日合算」パターン（port_ret_cc[t] ≈ ret_raw[t] + ret_raw[t-1]）を検査
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
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_port_ret_cc() -> pd.Series:
    """
    horizon_ensemble_variant_cross4.parquet から port_ret_cc を読み込む
    
    Returns
    -------
    pd.Series
        trade_dateをindexとするport_ret_cc
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


def load_daily_portfolio() -> pd.DataFrame:
    """
    daily_portfolio_guarded.parquet から weights を読み込む
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    portfolio_path = DATA_DIR / "daily_portfolio_guarded.parquet"
    
    if not portfolio_path.exists():
        raise FileNotFoundError(f"daily_portfolio_guarded.parquetが見つかりません: {portfolio_path}")
    
    df = pd.read_parquet(portfolio_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
    df[date_col] = pd.to_datetime(df[date_col])
    
    # 必須カラムを確認
    required_cols = ["symbol", "weight"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise KeyError(f"必須カラムが不足しています: {missing_cols}")
    
    return df


def reconstruct_port_ret_from_weights_and_prices(
    df_weights: pd.DataFrame,
    use_weight_lag: bool = False
) -> pd.Series:
    """
    weights と prices から port_ret_cc を再構築
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame
    use_weight_lag : bool
        Trueなら w[t-1] * r[t]、Falseなら w[t] * r[t] を使用
    
    Returns
    -------
    pd.Series
        trade_dateをindexとするポートフォリオリターン
    """
    print(f"  [INFO] 価格データを読み込み中...")
    
    # 価格データを読み込む
    df_prices_all = data_loader.load_prices()
    if df_prices_all is None or len(df_prices_all) == 0:
        raise ValueError("価格データが取得できませんでした")
    
    # 日付カラムを確認
    date_col = "date" if "date" in df_prices_all.columns else "trade_date"
    if date_col not in df_prices_all.columns:
        raise ValueError(f"日付カラムが見つかりません: {df_prices_all.columns.tolist()}")
    
    df_prices_all[date_col] = pd.to_datetime(df_prices_all[date_col])
    
    # adj_closeを使用（なければclose）
    if "adj_close" in df_prices_all.columns:
        price_col = "adj_close"
    elif "close" in df_prices_all.columns:
        price_col = "close"
    else:
        raise ValueError("価格カラム（adj_close/close）が見つかりません")
    
    # 銘柄リストを取得
    symbols = sorted(df_weights["symbol"].unique().tolist())
    print(f"  銘柄数: {len(symbols)}")
    
    # 価格データをフィルタ（symbol列でフィルタ）
    df_prices = df_prices_all[df_prices_all["symbol"].isin(symbols)].copy()
    
    # リターンを計算
    df_prices = df_prices.sort_values(["symbol", date_col])
    df_prices["ret_cc"] = df_prices.groupby("symbol")[price_col].pct_change()
    
    # 日付範囲を取得
    dates = sorted(df_weights[date_col].unique())
    print(f"  日数: {len(dates)}")
    
    # 各日についてポートフォリオリターンを計算
    port_ret_list = []
    
    for i, date in enumerate(dates):
        date_pd = pd.to_datetime(date).normalize()
        
        # weightsを取得
        if use_weight_lag and i > 0:
            # w[t-1]を使用
            prev_date = dates[i-1]
            weights_day = df_weights[df_weights[date_col] == prev_date].copy()
        else:
            # w[t]を使用
            weights_day = df_weights[df_weights[date_col] == date_pd].copy()
        
        if weights_day.empty:
            continue
        
        weights_series = weights_day.set_index("symbol")["weight"]
        
        # 当日のリターンを取得（r[t]）
        prices_day = df_prices[df_prices[date_col] == date_pd].copy()
        if prices_day.empty:
            continue
        
        rets_series = prices_day.set_index("symbol")["ret_cc"]
        
        # ポートフォリオリターンを計算: Σ w * r
        common_symbols = weights_series.index.intersection(rets_series.index)
        if len(common_symbols) == 0:
            continue
        
        port_ret = (weights_series.loc[common_symbols] * rets_series.loc[common_symbols]).sum()
        port_ret_list.append({
            date_col: date_pd,
            "port_ret_cc": port_ret,
        })
    
    df_result = pd.DataFrame(port_ret_list)
    if len(df_result) == 0:
        raise ValueError("ポートフォリオリターンが計算できませんでした")
    
    df_result = df_result.set_index(date_col)["port_ret_cc"].sort_index()
    
    return df_result


def verify_1_price_based_cc(df_port_ret_cc: pd.Series) -> pd.DataFrame:
    """
    検証1: port_ret_cc が priceからの生CCと一致するか
    
    Returns
    -------
    pd.DataFrame
        比較結果（date, port_ret_cc, price_based_ret_cc, diff, abs_diff）
    """
    print("\n" + "=" * 80)
    print("【検証1】port_ret_cc が priceからの生CC（adj_close.pct_change()）と一致するか")
    print("=" * 80)
    
    # daily_portfolioからweightsを読み込む
    print("\n[STEP 1-1] daily_portfolio_guarded.parquetを読み込み中...")
    try:
        df_weights = load_daily_portfolio()
        print(f"  ✓ {len(df_weights)} 行")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        print("  → daily_portfolio_guarded.parquetがない場合は検証1をスキップ")
        return pd.DataFrame()
    
    # weightsとpricesから再構築（w[t-1] * r[t]）
    print("\n[STEP 1-2] weightsとpricesからport_ret_ccを再構築中（w[t-1] * r[t]）...")
    try:
        port_ret_reconstructed = reconstruct_port_ret_from_weights_and_prices(df_weights, use_weight_lag=True)
        print(f"  ✓ {len(port_ret_reconstructed)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    
    # 比較
    common_dates = df_port_ret_cc.index.intersection(port_ret_reconstructed.index)
    df_comparison = pd.DataFrame({
        "date": common_dates,
        "port_ret_cc": df_port_ret_cc.loc[common_dates].values,
        "price_based_ret_cc": port_ret_reconstructed.loc[common_dates].values,
    })
    df_comparison["diff"] = df_comparison["port_ret_cc"] - df_comparison["price_based_ret_cc"]
    df_comparison["abs_diff"] = df_comparison["diff"].abs()
    
    # 統計
    match_count = (df_comparison["abs_diff"] <= 1e-8).sum()
    match_ratio = match_count / len(df_comparison) if len(df_comparison) > 0 else 0.0
    mean_abs_diff = df_comparison["abs_diff"].mean()
    max_abs_diff = df_comparison["abs_diff"].max()
    
    print(f"\n[結果]")
    print(f"  比較日数: {len(df_comparison)}")
    print(f"  完全一致（1e-8以内）: {match_count} 日 ({match_ratio:.2%})")
    print(f"  平均絶対差分: {mean_abs_diff:.10f}")
    print(f"  最大絶対差分: {max_abs_diff:.10f}")
    
    # Top差分日を表示
    if len(df_comparison) > 0:
        top_diff = df_comparison.nlargest(10, "abs_diff")
        print(f"\n  [Top 10 差分日]")
        for _, row in top_diff.iterrows():
            print(f"    {row['date'].date()}: port_ret_cc={row['port_ret_cc']:.8f}, price_based={row['price_based_ret_cc']:.8f}, diff={row['diff']:.8f}")
    
    return df_comparison


def verify_2_weight_lag(df_port_ret_cc: pd.Series) -> dict:
    """
    検証2: port_ret_cc が w×r から作られている場合、w[t] か w[t-1] かを特定
    
    Returns
    -------
    dict
        比較結果
    """
    print("\n" + "=" * 80)
    print("【検証2】port_ret_cc が w×r から作られている場合、w[t] か w[t-1] かを特定")
    print("=" * 80)
    
    # daily_portfolioからweightsを読み込む
    print("\n[STEP 2-1] daily_portfolio_guarded.parquetを読み込み中...")
    try:
        df_weights = load_daily_portfolio()
        print(f"  ✓ {len(df_weights)} 行")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return {"error": str(e)}
    
    # w[t] * r[t] で再構築
    print("\n[STEP 2-2] w[t] * r[t] で再構築中...")
    try:
        port_ret_w_t = reconstruct_port_ret_from_weights_and_prices(df_weights, use_weight_lag=False)
        print(f"  ✓ {len(port_ret_w_t)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return {"error": str(e)}
    
    # w[t-1] * r[t] で再構築
    print("\n[STEP 2-3] w[t-1] * r[t] で再構築中...")
    try:
        port_ret_w_t_1 = reconstruct_port_ret_from_weights_and_prices(df_weights, use_weight_lag=True)
        print(f"  ✓ {len(port_ret_w_t_1)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return {"error": str(e)}
    
    # 比較
    common_dates = df_port_ret_cc.index.intersection(port_ret_w_t.index).intersection(port_ret_w_t_1.index)
    
    diff_w_t = (df_port_ret_cc.loc[common_dates] - port_ret_w_t.loc[common_dates]).abs()
    diff_w_t_1 = (df_port_ret_cc.loc[common_dates] - port_ret_w_t_1.loc[common_dates]).abs()
    
    match_w_t = (diff_w_t <= 1e-8).sum()
    match_w_t_1 = (diff_w_t_1 <= 1e-8).sum()
    match_ratio_w_t = match_w_t / len(common_dates) if len(common_dates) > 0 else 0.0
    match_ratio_w_t_1 = match_w_t_1 / len(common_dates) if len(common_dates) > 0 else 0.0
    
    mean_diff_w_t = diff_w_t.mean()
    mean_diff_w_t_1 = diff_w_t_1.mean()
    
    print(f"\n[結果]")
    print(f"  比較日数: {len(common_dates)}")
    print(f"\n  w[t] * r[t] の場合:")
    print(f"    完全一致: {match_w_t} 日 ({match_ratio_w_t:.2%})")
    print(f"    平均絶対差分: {mean_diff_w_t:.10f}")
    print(f"\n  w[t-1] * r[t] の場合:")
    print(f"    完全一致: {match_w_t_1} 日 ({match_ratio_w_t_1:.2%})")
    print(f"    平均絶対差分: {mean_diff_w_t_1:.10f}")
    
    # 判定
    if match_ratio_w_t_1 > match_ratio_w_t:
        print(f"\n  → 判定: w[t-1] * r[t] の方が一致率が高い（正しい）")
        winner = "w[t-1] * r[t]"
    elif match_ratio_w_t > match_ratio_w_t_1:
        print(f"\n  → 判定: w[t] * r[t] の方が一致率が高い（look-ahead混入の可能性）")
        winner = "w[t] * r[t]"
    else:
        print(f"\n  → 判定: どちらも同等")
        winner = "不明"
    
    return {
        "comparison_dates": len(common_dates),
        "match_w_t": match_w_t,
        "match_ratio_w_t": match_ratio_w_t,
        "mean_diff_w_t": mean_diff_w_t,
        "match_w_t_1": match_w_t_1,
        "match_ratio_w_t_1": match_ratio_w_t_1,
        "mean_diff_w_t_1": mean_diff_w_t_1,
        "winner": winner,
    }


def verify_3_two_day_sum_pattern(df_port_ret_cc: pd.Series) -> pd.DataFrame:
    """
    検証3: 「2日合算」パターン（port_ret_cc[t] ≈ ret_raw[t] + ret_raw[t-1]）を検査
    
    Returns
    -------
    pd.DataFrame
        2日合算パターンが疑われる日のリスト
    """
    print("\n" + "=" * 80)
    print("【検証3】「2日合算」パターン（port_ret_cc[t] ≈ ret_raw[t] + ret_raw[t-1]）を検査")
    print("=" * 80)
    
    # daily_portfolioからweightsを読み込む
    print("\n[STEP 3-1] daily_portfolio_guarded.parquetを読み込み中...")
    try:
        df_weights = load_daily_portfolio()
        print(f"  ✓ {len(df_weights)} 行")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return pd.DataFrame()
    
    # weightsとpricesから再構築（w[t-1] * r[t]）
    print("\n[STEP 3-2] weightsとpricesからret_rawを再構築中...")
    try:
        port_ret_raw = reconstruct_port_ret_from_weights_and_prices(df_weights, use_weight_lag=True)
        print(f"  ✓ {len(port_ret_raw)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return pd.DataFrame()
    
    # 2日合算パターンを検査
    common_dates = df_port_ret_cc.index.intersection(port_ret_raw.index)
    
    # ret_raw[t] + ret_raw[t-1] を計算
    port_ret_raw_shifted = port_ret_raw.shift(1)
    port_ret_two_day_sum = port_ret_raw.loc[common_dates] + port_ret_raw_shifted.loc[common_dates]
    
    # port_ret_cc[t] と ret_raw[t] + ret_raw[t-1] を比較
    df_comparison = pd.DataFrame({
        "date": common_dates,
        "port_ret_cc": df_port_ret_cc.loc[common_dates].values,
        "ret_raw_t": port_ret_raw.loc[common_dates].values,
        "ret_raw_t_1": port_ret_raw_shifted.loc[common_dates].values,
        "ret_two_day_sum": port_ret_two_day_sum.values,
    })
    df_comparison["diff_from_two_day_sum"] = df_comparison["port_ret_cc"] - df_comparison["ret_two_day_sum"]
    df_comparison["abs_diff_from_two_day_sum"] = df_comparison["diff_from_two_day_sum"].abs()
    
    # 2日合算パターンが疑われる日（差分が小さい）を抽出
    threshold = 0.01  # 1%以内なら2日合算と判定
    suspect_days = df_comparison[df_comparison["abs_diff_from_two_day_sum"] <= threshold].copy()
    
    print(f"\n[結果]")
    print(f"  比較日数: {len(df_comparison)}")
    print(f"  2日合算パターンが疑われる日（差分{threshold:.1%}以内）: {len(suspect_days)} 日")
    
    if len(suspect_days) > 0:
        suspect_ratio = len(suspect_days) / len(df_comparison)
        print(f"  疑わしい日の割合: {suspect_ratio:.2%}")
        
        # Top 20を表示
        top_suspect = suspect_days.nsmallest(20, "abs_diff_from_two_day_sum")
        print(f"\n  [Top 20 2日合算パターンが疑われる日]")
        for _, row in top_suspect.iterrows():
            print(f"    {row['date'].date()}: port_ret_cc={row['port_ret_cc']:.8f}, two_day_sum={row['ret_two_day_sum']:.8f}, diff={row['diff_from_two_day_sum']:.8f}")
    
    return suspect_days


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== port_ret_cc が ret_raw[t] であるかの検証 ===")
    print("=" * 80)
    
    # port_ret_ccを読み込む
    print("\n[STEP 0] horizon_ensemble_variant_cross4.parquetからport_ret_ccを読み込み中...")
    try:
        port_ret_cc = load_port_ret_cc()
        print(f"  ✓ {len(port_ret_cc)} 日分")
        print(f"  期間: {port_ret_cc.index.min().date()} ～ {port_ret_cc.index.max().date()}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 検証1: price-based CCとの一致
    result_1 = verify_1_price_based_cc(port_ret_cc)
    
    # 検証2: weight lagの特定
    result_2 = verify_2_weight_lag(port_ret_cc)
    
    # 検証3: 2日合算パターン
    result_3 = verify_3_two_day_sum_pattern(port_ret_cc)
    
    # 結果をCSVに保存
    if len(result_1) > 0:
        output_path_1 = RESEARCH_REPORTS_DIR / "verify_port_ret_cc_price_based_comparison.csv"
        result_1.to_csv(output_path_1, index=False)
        print(f"\n✓ 検証1の結果を保存: {output_path_1}")
    
    if isinstance(result_2, dict) and "error" not in result_2:
        output_path_2 = RESEARCH_REPORTS_DIR / "verify_port_ret_cc_weight_lag_summary.csv"
        pd.DataFrame([result_2]).to_csv(output_path_2, index=False)
        print(f"✓ 検証2の結果を保存: {output_path_2}")
    
    if len(result_3) > 0:
        output_path_3 = RESEARCH_REPORTS_DIR / "verify_port_ret_cc_two_day_sum_suspects.csv"
        result_3.to_csv(output_path_3, index=False)
        print(f"✓ 検証3の結果を保存: {output_path_3}")
    
    # 2024-08-05が含まれているかチェック
    target_date = pd.to_datetime("2024-08-05").normalize()
    if target_date in port_ret_cc.index:
        print(f"\n【2024-08-05の確認】")
        print(f"  port_ret_cc[{target_date.date()}]: {port_ret_cc.loc[target_date]:.8f}")
        
        if len(result_1) > 0 and target_date in result_1["date"].values:
            row = result_1[result_1["date"] == target_date].iloc[0]
            print(f"  price_based_ret_cc: {row['price_based_ret_cc']:.8f}")
            print(f"  差分: {row['diff']:.8f}")
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

