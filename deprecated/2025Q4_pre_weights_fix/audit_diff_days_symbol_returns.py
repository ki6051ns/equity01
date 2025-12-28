#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/audit_diff_days_symbol_returns.py

weights版 vs eval版 の乖離が大きい日について、銘柄別日次リターンを詳細点検

目的：
- 異常リターンが現実の市場変動なのか、データ取り扱いの問題（adj_close、日付ズレ、欠損埋め、スプリット等）なのかを確定
- 仮説A（日付ズレ）、仮説B（adj_close不整合）、仮説C（欠損埋め）、仮説D（保有銘柄外）を切り分け

入力:
- data/processed/research/reports/stop_cross4_equivalence_detail_{strategy}_w{window}.parquet（差分詳細）
- data/processed/weights/cross4_target_weights_{strategy}_w{window}.parquet（weights）
- 価格データ（close/adj_close）

出力:
- data/processed/research/reports/diff_days_symbol_return_audit_{strategy}_w{window}.parquet
- data/processed/research/reports/diff_days_symbol_return_audit_{strategy}_w{window}.csv
- data/processed/research/reports/diff_days_symbol_return_audit_{strategy}_w{window}_summary.csv
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
from scripts.tools import data_loader

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_top_diff_dates(
    strategy: str,
    window: int = None,
    top_n: int = 30,
    min_diff: float = None
) -> pd.DataFrame:
    """
    verify_stop_cross4_equivalence.pyの出力からTop差分日を取得
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int, optional
        ウィンドウサイズ
    top_n : int
        Top N日を取得（デフォルト: 30）
    min_diff : float, optional
        最小差分（これ以上の日のみ）
    
    Returns
    -------
    pd.DataFrame
        trade_date, abs_diff, port_ret_cc_weights, port_ret_cc_eval, diff を含むDataFrame
    """
    if window is not None:
        window_str = f"w{window}"
        detail_path = RESEARCH_REPORTS_DIR / f"stop_cross4_equivalence_detail_{strategy}_{window_str}.parquet"
    else:
        window_str = "baseline"
        detail_path = RESEARCH_REPORTS_DIR / f"stop_cross4_equivalence_detail_{strategy}_{window_str}.parquet"
    
    if not detail_path.exists():
        raise FileNotFoundError(f"差分詳細ファイルが見つかりません: {detail_path}\n先に verify_stop_cross4_equivalence.py を実行してください。")
    
    df_detail = pd.read_parquet(detail_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["trade_date", "date"]:
        if col in df_detail.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df_detail.columns.tolist()}")
    
    df_detail[date_col] = pd.to_datetime(df_detail[date_col])
    
    # abs_diff列を確認（なければ計算）
    if "abs_diff" not in df_detail.columns:
        if "diff" in df_detail.columns:
            df_detail["abs_diff"] = df_detail["diff"].abs()
        else:
            raise KeyError(f"abs_diff/diff列が見つかりません: {df_detail.columns.tolist()}")
    
    # ソートしてTop Nを取得
    df_top = df_detail.nlargest(top_n, "abs_diff", keep="all").copy()
    
    # 最小差分フィルタ
    if min_diff is not None:
        df_top = df_top[df_top["abs_diff"] >= min_diff].copy()
    
    df_top = df_top.sort_values("abs_diff", ascending=False)
    
    return df_top


def load_prices_with_adj(symbols: list, date_start: pd.Timestamp, date_end: pd.Timestamp) -> pd.DataFrame:
    """
    銘柄リストの価格データ（close/adj_close）を読み込む
    
    Parameters
    ----------
    symbols : list
        銘柄リスト
    date_start : pd.Timestamp
        開始日
    date_end : pd.Timestamp
        終了日
    
    Returns
    -------
    pd.DataFrame
        trade_date, symbol, close, adj_close を含むDataFrame
    """
    print(f"  [INFO] 価格データを読み込み中（{len(symbols)}銘柄、{date_start.date()} ～ {date_end.date()}）...")
    
    try:
        df_prices_all = data_loader.load_prices()
        if df_prices_all is None or len(df_prices_all) == 0:
            raise ValueError("価格データが取得できませんでした")
        
        # 日付カラムを確認
        date_col = "date" if "date" in df_prices_all.columns else "trade_date"
        if date_col not in df_prices_all.columns:
            raise ValueError(f"日付カラムが見つかりません: {df_prices_all.columns.tolist()}")
        
        df_prices_all[date_col] = pd.to_datetime(df_prices_all[date_col])
        
        # 指定銘柄のみをフィルタ
        if "symbol" in df_prices_all.columns:
            df_prices = df_prices_all[df_prices_all["symbol"].isin(symbols)].copy()
        else:
            raise ValueError("symbol列が見つかりません")
        
        # 日付でフィルタ
        df_prices = df_prices[
            (df_prices[date_col] >= date_start) & 
            (df_prices[date_col] <= date_end)
        ].copy()
        
        # カラム名を統一（trade_date）
        if date_col != "trade_date":
            df_prices = df_prices.rename(columns={date_col: "trade_date"})
        
        # close/adj_closeを確認
        if "close" not in df_prices.columns:
            raise ValueError("close列が見つかりません")
        
        if "adj_close" not in df_prices.columns:
            # adj_closeがない場合はcloseをコピー
            print(f"  [WARN] adj_close列が見つかりません。closeをコピーします。")
            df_prices["adj_close"] = df_prices["close"]
        
        # ソート
        df_prices = df_prices.sort_values(["symbol", "trade_date"])
        
        return df_prices
        
    except Exception as e:
        print(f"  [ERROR] 価格データ読み込みエラー: {e}")
        import traceback
        traceback.print_exc()
        raise


def load_weights_for_dates(weights_path: Path, target_dates: list) -> pd.DataFrame:
    """
    指定日のweightsを読み込む
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス
    target_dates : list
        対象日リスト
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    df_weights = pd.read_parquet(weights_path)
    df_weights["date"] = pd.to_datetime(df_weights["date"])
    
    # 対象日を正規化
    target_dates_pd = [pd.to_datetime(d).normalize() for d in target_dates]
    
    # 対象日とその前日を抽出
    dates_to_load = set(target_dates_pd)
    
    # 各対象日の前日を追加
    for target_date in target_dates_pd:
        dates_before = df_weights[df_weights["date"] < target_date]["date"].unique()
        if len(dates_before) > 0:
            prev_date = pd.to_datetime(max(dates_before)).normalize()
            dates_to_load.add(prev_date)
    
    dates_to_load = sorted(list(dates_to_load))
    
    df_selected = df_weights[df_weights["date"].isin(dates_to_load)].copy()
    
    return df_selected


def calculate_returns_with_flags(
    df_prices: pd.DataFrame,
    target_date: pd.Timestamp,
    symbols: list
) -> pd.DataFrame:
    """
    指定日のリターンを計算（close/adj_close両方）し、各種フラグを付与
    
    Parameters
    ----------
    df_prices : pd.DataFrame
        価格データ
    target_date : pd.Timestamp
        対象日
    symbols : list
        銘柄リスト
    
    Returns
    -------
    pd.DataFrame
        銘柄別リターンとフラグを含むDataFrame
    """
    target_date_pd = pd.to_datetime(target_date).normalize()
    
    # 対象日と前日の価格を抽出
    prices_target = df_prices[df_prices["trade_date"] == target_date_pd].set_index("symbol")
    
    # 前営業日を取得
    dates_before = sorted(df_prices[df_prices["trade_date"] < target_date_pd]["trade_date"].unique())
    if len(dates_before) > 0:
        prev_date = pd.to_datetime(max(dates_before))
        prices_prev = df_prices[df_prices["trade_date"] == prev_date].set_index("symbol")
    else:
        prev_date = None
        prices_prev = pd.DataFrame()
    
    # 翌営業日も取得（日付ズレチェック用）
    dates_after = sorted(df_prices[df_prices["trade_date"] > target_date_pd]["trade_date"].unique())
    if len(dates_after) > 0:
        next_date = pd.to_datetime(min(dates_after))
        prices_next = df_prices[df_prices["trade_date"] == next_date].set_index("symbol")
    else:
        next_date = None
        prices_next = pd.DataFrame()
    
    # さらに前の営業日（2日分合算チェック用）
    if prev_date is not None:
        dates_before_prev = sorted(df_prices[df_prices["trade_date"] < prev_date]["trade_date"].unique())
        if len(dates_before_prev) > 0:
            prev2_date = pd.to_datetime(max(dates_before_prev))
            prices_prev2 = df_prices[df_prices["trade_date"] == prev2_date].set_index("symbol")
        else:
            prev2_date = None
            prices_prev2 = pd.DataFrame()
    else:
        prev2_date = None
        prices_prev2 = pd.DataFrame()
    
    # 日数差を計算
    if prev_date is not None:
        days_gap = (target_date_pd - prev_date).days
    else:
        days_gap = None
    
    # 銘柄ごとにリターンとフラグを計算
    result_rows = []
    for symbol in symbols:
        # 対象日の価格
        if symbol in prices_target.index and "close" in prices_target.columns:
            close_D = prices_target.loc[symbol, "close"]
            adj_D = prices_target.loc[symbol, "adj_close"] if "adj_close" in prices_target.columns else prices_target.loc[symbol, "close"]
        else:
            close_D = np.nan
            adj_D = np.nan
        
        # 前日の価格
        if prev_date is not None and len(prices_prev) > 0 and symbol in prices_prev.index and "close" in prices_prev.columns:
            close_Dprev = prices_prev.loc[symbol, "close"]
            adj_Dprev = prices_prev.loc[symbol, "adj_close"] if "adj_close" in prices_prev.columns else prices_prev.loc[symbol, "close"]
        else:
            close_Dprev = np.nan
            adj_Dprev = np.nan
        
        # 翌日の価格（日付ズレチェック用）
        if next_date is not None and len(prices_next) > 0 and symbol in prices_next.index and "close" in prices_next.columns:
            close_Dnext = prices_next.loc[symbol, "close"]
            adj_Dnext = prices_next.loc[symbol, "adj_close"] if "adj_close" in prices_next.columns else prices_next.loc[symbol, "close"]
        else:
            close_Dnext = np.nan
            adj_Dnext = np.nan
        
        # さらに前の日の価格
        if prev2_date is not None and len(prices_prev2) > 0 and symbol in prices_prev2.index and "close" in prices_prev2.columns:
            close_Dprev2 = prices_prev2.loc[symbol, "close"]
            adj_Dprev2 = prices_prev2.loc[symbol, "adj_close"] if "adj_close" in prices_prev2.columns else prices_prev2.loc[symbol, "close"]
        else:
            close_Dprev2 = np.nan
            adj_Dprev2 = np.nan
        
        # リターンを計算
        ret_close = np.nan
        ret_adj = np.nan
        if not np.isnan(close_D) and not np.isnan(close_Dprev) and close_Dprev != 0:
            ret_close = (close_D - close_Dprev) / close_Dprev
        
        if not np.isnan(adj_D) and not np.isnan(adj_Dprev) and adj_Dprev != 0:
            ret_adj = (adj_D - adj_Dprev) / adj_Dprev
        
        # フラグを設定
        prev_missing = np.isnan(close_Dprev) or np.isnan(adj_Dprev)
        price_zero = (not np.isnan(close_D) and close_D == 0) or (not np.isnan(adj_D) and adj_D == 0)
        prev_zero = (not np.isnan(close_Dprev) and close_Dprev == 0) or (not np.isnan(adj_Dprev) and adj_Dprev == 0)
        
        abnormal_15 = abs(ret_close) >= 0.15 if not np.isnan(ret_close) else False
        abnormal_20 = abs(ret_close) >= 0.20 if not np.isnan(ret_close) else False
        abnormal_25 = abs(ret_close) >= 0.25 if not np.isnan(ret_close) else False
        
        # adj_close不整合チェック（仮説B）
        adj_close_suspect = False
        if not np.isnan(ret_close) and not np.isnan(ret_adj):
            ret_diff = abs(ret_close - ret_adj)
            if ret_diff > 0.05:  # 5%以上の差
                adj_close_suspect = True
        
        # 日付ズレチェック（仮説A）：当日リターンが翌日リターンに近い
        date_shift_suspect = False
        if not np.isnan(ret_close) and not np.isnan(close_Dnext) and not np.isnan(close_Dprev) and close_Dprev != 0:
            ret_next = (close_Dnext - close_D) / close_D if close_D != 0 else np.nan
            if not np.isnan(ret_next):
                # 当日リターンと翌日リターンが似ている（符号が同じで大きさが近い）
                if abs(ret_close - ret_next) < 0.01 and ret_close * ret_next > 0:
                    date_shift_suspect = True
        
        # 2日分合算疑い
        suspect_2day_sum = False
        if not np.isnan(ret_close) and not np.isnan(close_Dprev2) and not np.isnan(close_Dprev) and close_Dprev != 0:
            ret_prev = (close_Dprev - close_Dprev2) / close_Dprev2 if close_Dprev2 != 0 else np.nan
            if not np.isnan(ret_prev):
                expected_2day = (1.0 + ret_prev) * (1.0 + ret_close) - 1.0
                if abs(ret_close - expected_2day) < 0.01:
                    suspect_2day_sum = True
        
        result_rows.append({
            "symbol": symbol,
            "close_Dprev": close_Dprev,
            "close_D": close_D,
            "adj_Dprev": adj_Dprev,
            "adj_D": adj_D,
            "ret_close": ret_close,
            "ret_adj": ret_adj,
            "prev_missing": prev_missing,
            "price_zero": price_zero,
            "prev_zero": prev_zero,
            "abnormal_15": abnormal_15,
            "abnormal_20": abnormal_20,
            "abnormal_25": abnormal_25,
            "adj_close_suspect": adj_close_suspect,
            "date_shift_suspect": date_shift_suspect,
            "suspect_2day_sum": suspect_2day_sum,
            "days_gap": days_gap,
        })
    
    df_returns = pd.DataFrame(result_rows)
    df_returns["target_date"] = target_date_pd
    df_returns["prev_date"] = prev_date
    df_returns["next_date"] = next_date
    
    return df_returns


def audit_dates(
    strategy: str,
    window: int = None,
    top_n: int = 30,
    min_diff: float = None,
    return_threshold: float = 0.15
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    複数日をバッチ処理して銘柄別リターンを点検
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int, optional
        ウィンドウサイズ
    top_n : int
        Top N日を取得
    min_diff : float, optional
        最小差分
    return_threshold : float
        異常リターンの閾値
    
    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        (銘柄別詳細, 日別サマリー)
    """
    print("=" * 80)
    print(f"=== 銘柄別リターン点検（複数日バッチ） ===")
    print("=" * 80)
    print(f"\n戦略: {strategy}")
    if window is not None:
        print(f"Window: {window}")
        window_str = f"w{window}"
        weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_{window_str}.parquet"
    else:
        window_str = "baseline"
        weights_path = WEIGHTS_DIR / "cross4_target_weights.parquet"
    
    # Top差分日を取得
    print(f"\n[STEP 1] Top差分日を取得中...")
    df_top_dates = load_top_diff_dates(strategy, window, top_n=top_n, min_diff=min_diff)
    target_dates = sorted(df_top_dates["trade_date"].unique())
    print(f"  ✓ {len(target_dates)} 日")
    print(f"  最大差分: {df_top_dates['abs_diff'].max():.8f}")
    print(f"  対象日範囲: {target_dates[0].date()} ～ {target_dates[-1].date()}")
    
    # weightsを読み込む
    print(f"\n[STEP 2] weightsを読み込み中...")
    if not weights_path.exists():
        raise FileNotFoundError(f"weightsファイルが見つかりません: {weights_path}")
    df_weights_all = load_weights_for_dates(weights_path, target_dates)
    print(f"  ✓ {len(df_weights_all)} 行")
    
    # 全銘柄リストを取得
    all_symbols = sorted(df_weights_all["symbol"].unique().tolist())
    print(f"  銘柄数: {len(all_symbols)}")
    
    # 価格データを読み込む（余裕を持って前後数日を含む）
    print(f"\n[STEP 3] 価格データを読み込み中...")
    date_start = pd.to_datetime(target_dates[0]) - pd.Timedelta(days=5)
    date_end = pd.to_datetime(target_dates[-1]) + pd.Timedelta(days=5)
    df_prices = load_prices_with_adj(all_symbols, date_start, date_end)
    print(f"  ✓ {len(df_prices)} 行")
    
    # 各日について銘柄別リターンを計算
    print(f"\n[STEP 4] 各日の銘柄別リターンを計算中...")
    all_results = []
    
    for i, target_date in enumerate(target_dates):
        print(f"  処理中: {target_date.date()} ({i+1}/{len(target_dates)})")
        
        # 対象日のweights
        target_date_pd = pd.to_datetime(target_date).normalize()
        weights_t = df_weights_all[df_weights_all["date"] == target_date_pd].set_index("symbol")["weight"]
        
        # 前日のweights
        dates_before = df_weights_all[df_weights_all["date"] < target_date_pd]["date"].unique()
        if len(dates_before) > 0:
            prev_date = pd.to_datetime(max(dates_before)).normalize()
            weights_t_1 = df_weights_all[df_weights_all["date"] == prev_date].set_index("symbol")["weight"]
        else:
            weights_t_1 = pd.Series(dtype=float)
        
        # リターンとフラグを計算
        df_returns = calculate_returns_with_flags(df_prices, target_date, all_symbols)
        
        # weightsとマージ
        df_returns["weight_t"] = df_returns["symbol"].map(weights_t).fillna(0.0)
        df_returns["weight_t_1"] = df_returns["symbol"].map(weights_t_1).fillna(0.0)
        
        # 寄与を計算
        df_returns["contribution_close"] = df_returns["weight_t"] * df_returns["ret_close"]
        df_returns["contribution_adj"] = df_returns["weight_t"] * df_returns["ret_adj"]
        df_returns["contribution_t_1_close"] = df_returns["weight_t_1"] * df_returns["ret_close"]
        df_returns["contribution_t_1_adj"] = df_returns["weight_t_1"] * df_returns["ret_adj"]
        
        # 保有銘柄フラグ
        df_returns["is_held"] = df_returns["weight_t"] > 0.0
        
        # 差分情報を追加
        diff_info = df_top_dates[df_top_dates["trade_date"] == target_date].iloc[0]
        df_returns["abs_diff"] = diff_info["abs_diff"]
        df_returns["port_ret_weights"] = diff_info.get("port_ret_cc_weights", np.nan)
        df_returns["port_ret_eval"] = diff_info.get("port_ret_cc_eval", np.nan)
        df_returns["diff"] = diff_info.get("diff", np.nan)
        
        all_results.append(df_returns)
    
    # 全結果を結合
    df_all = pd.concat(all_results, ignore_index=True)
    
    # 日別サマリーを作成
    print(f"\n[STEP 5] 日別サマリーを作成中...")
    summary_rows = []
    for target_date in target_dates:
        target_date_pd = pd.to_datetime(target_date).normalize()
        df_day = df_all[df_all["target_date"] == target_date_pd].copy()
        
        # 保有銘柄のみで集計
        df_held = df_day[df_day["is_held"]].copy()
        
        summary_rows.append({
            "date": target_date_pd,
            "abs_diff": df_day["abs_diff"].iloc[0] if len(df_day) > 0 else np.nan,
            "port_ret_weights": df_day["port_ret_weights"].iloc[0] if len(df_day) > 0 else np.nan,
            "port_ret_eval": df_day["port_ret_eval"].iloc[0] if len(df_day) > 0 else np.nan,
            "diff": df_day["diff"].iloc[0] if len(df_day) > 0 else np.nan,
            "num_symbols_total": len(df_day),
            "num_symbols_held": len(df_held),
            "abnormal_15_held": df_held["abnormal_15"].sum() if len(df_held) > 0 else 0,
            "abnormal_20_held": df_held["abnormal_20"].sum() if len(df_held) > 0 else 0,
            "abnormal_25_held": df_held["abnormal_25"].sum() if len(df_held) > 0 else 0,
            "abnormal_15_total": df_day["abnormal_15"].sum() if len(df_day) > 0 else 0,
            "abnormal_20_total": df_day["abnormal_20"].sum() if len(df_day) > 0 else 0,
            "abnormal_25_total": df_day["abnormal_25"].sum() if len(df_day) > 0 else 0,
            "max_ret_close": df_held["ret_close"].abs().max() if len(df_held) > 0 and df_held["ret_close"].notna().any() else np.nan,
            "max_ret_adj": df_held["ret_adj"].abs().max() if len(df_held) > 0 and df_held["ret_adj"].notna().any() else np.nan,
            "mean_ret_diff": df_held["ret_close"].sub(df_held["ret_adj"]).abs().mean() if len(df_held) > 0 else np.nan,
            "prev_missing_count": df_held["prev_missing"].sum() if len(df_held) > 0 else 0,
            "price_zero_count": df_held["price_zero"].sum() if len(df_held) > 0 else 0,
            "adj_close_suspect_count": df_held["adj_close_suspect"].sum() if len(df_held) > 0 else 0,
            "date_shift_suspect_count": df_held["date_shift_suspect"].sum() if len(df_held) > 0 else 0,
        })
    
    df_summary = pd.DataFrame(summary_rows)
    
    return df_all, df_summary


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="weights版 vs eval版 の乖離が大きい日について銘柄別リターンを点検"
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
        "--top-n",
        type=int,
        default=30,
        help="Top N日を取得（デフォルト: 30）"
    )
    parser.add_argument(
        "--min-diff",
        type=float,
        default=None,
        help="最小差分（これ以上の日のみ取得）"
    )
    
    args = parser.parse_args()
    
    if args.strategy != "baseline" and args.window is None:
        parser.error("--window は baseline以外では必須です")
    
    try:
        # バッチ処理実行
        df_detail, df_summary = audit_dates(
            args.strategy,
            args.window,
            top_n=args.top_n,
            min_diff=args.min_diff
        )
        
        # ファイル名
        if args.window is not None:
            window_str = f"w{args.window}"
        else:
            window_str = "baseline"
        
        base_name = f"diff_days_symbol_return_audit_{args.strategy}_{window_str}"
        
        # 詳細を保存
        detail_path_parquet = RESEARCH_REPORTS_DIR / f"{base_name}.parquet"
        detail_path_csv = RESEARCH_REPORTS_DIR / f"{base_name}.csv"
        df_detail.to_parquet(detail_path_parquet, index=False)
        df_detail.to_csv(detail_path_csv, index=False)
        print(f"\n✓ 詳細を保存:")
        print(f"  {detail_path_parquet}")
        print(f"  {detail_path_csv}")
        
        # サマリーを保存
        summary_path = RESEARCH_REPORTS_DIR / f"{base_name}_summary.csv"
        df_summary.to_csv(summary_path, index=False)
        print(f"\n✓ サマリーを保存: {summary_path}")
        
        # サマリーを表示
        print("\n" + "=" * 80)
        print("【日別サマリー（Top 10）】")
        print("=" * 80)
        print(df_summary.head(10).to_string(index=False, float_format="%.6f"))
        
        print("\n" + "=" * 80)
        print("完了")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

