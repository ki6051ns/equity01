#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/debug_diff_day_attribution.py

STOP付cross4のweights版とeval版の差分が最大の日について、
銘柄別寄与（w×r）を分解して原因を特定する

入力:
- data/processed/weights_bt/cross4_from_weights_{strategy}_w{window}.parquet（weights版returns）
- data/processed/stop_regime_strategies.parquet（eval版returns）
- data/processed/weights/cross4_target_weights_{strategy}_w{window}.parquet（weights）
- 価格データ（個別銘柄の日次価格）

出力:
- 乖離最大日の特定
- 銘柄別寄与テーブル（return、weight_t、weight_t_1、contribution等）
- 周辺日のログ
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
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_returns_comparison(strategy: str, window: int = None) -> pd.DataFrame:
    """
    weights版とeval版のreturnsを読み込んで差分を計算
    
    Parameters
    ----------
    strategy : str
        "baseline", "stop0", "planA", "planB" のいずれか
    window : int, optional
        ウィンドウサイズ（baselineの場合はNone）
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc_weights, port_ret_cc_eval, diff, abs_diff を含むDataFrame
    """
    # weights版のreturnsを読み込む
    if strategy == "baseline":
        weights_path = WEIGHTS_BT_DIR / "cross4_from_weights.parquet"
    else:
        weights_path = WEIGHTS_BT_DIR / f"cross4_from_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        raise FileNotFoundError(f"weights版returnsファイルが見つかりません: {weights_path}")
    
    df_weights = pd.read_parquet(weights_path)
    df_weights["trade_date"] = pd.to_datetime(df_weights["trade_date"])
    
    # eval版のreturnsを読み込む
    if strategy == "baseline":
        eval_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
        if not eval_path.exists():
            raise FileNotFoundError(f"eval版returnsファイルが見つかりません: {eval_path}")
        df_eval = pd.read_parquet(eval_path)
        df_eval["trade_date"] = pd.to_datetime(df_eval["trade_date"])
        if "port_ret_cc" not in df_eval.columns:
            raise KeyError(f"port_ret_cc列が見つかりません: {df_eval.columns.tolist()}")
        df_eval = df_eval[["trade_date", "port_ret_cc"]]
    else:
        eval_path = DATA_DIR / "stop_regime_strategies.parquet"
        if not eval_path.exists():
            raise FileNotFoundError(f"eval版returnsファイルが見つかりません: {eval_path}")
        df_eval = pd.read_parquet(eval_path)
        date_col = "date" if "date" in df_eval.columns else "trade_date"
        df_eval[date_col] = pd.to_datetime(df_eval[date_col])
        ret_col = f"{strategy}_{window}"
        if ret_col not in df_eval.columns:
            raise KeyError(f"リターン列 '{ret_col}' が見つかりません")
        df_eval = df_eval[[date_col, ret_col]].rename(columns={date_col: "trade_date", ret_col: "port_ret_cc"})
    
    # マージして差分を計算
    df_merged = df_weights[["trade_date", "port_ret_cc"]].merge(
        df_eval[["trade_date", "port_ret_cc"]],
        on="trade_date",
        how="inner",
        suffixes=("_weights", "_eval")
    )
    
    df_merged["diff"] = df_merged["port_ret_cc_weights"] - df_merged["port_ret_cc_eval"]
    df_merged["abs_diff"] = df_merged["diff"].abs()
    
    return df_merged


def find_max_diff_date(df_comparison: pd.DataFrame) -> pd.Timestamp:
    """
    差分が最大の日を特定
    
    Parameters
    ----------
    df_comparison : pd.DataFrame
        compare_returnsの出力（diff, abs_diff列を含む）
    
    Returns
    -------
    pd.Timestamp
        差分が最大の日付
    """
    max_idx = df_comparison["abs_diff"].idxmax()
    max_date = df_comparison.loc[max_idx, "trade_date"]
    return pd.to_datetime(max_date)


def load_weights_for_date(weights_path: Path, target_date: pd.Timestamp) -> pd.DataFrame:
    """
    指定日のweightsを読み込む（前日も含む）
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス
    target_date : pd.Timestamp
        対象日
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame（target_dateと前日の両方）
    """
    df_weights = pd.read_parquet(weights_path)
    df_weights["date"] = pd.to_datetime(df_weights["date"])
    
    # 対象日と前日を抽出
    target_date_pd = pd.to_datetime(target_date).normalize()
    
    # 前日の営業日を取得（対象日より前の最新日）
    dates_before = df_weights[df_weights["date"] < target_date_pd]["date"].unique()
    if len(dates_before) > 0:
        prev_date = pd.to_datetime(max(dates_before)).normalize()
    else:
        prev_date = None
    
    # 対象日と前日のweightsを抽出
    dates_to_load = [target_date_pd]
    if prev_date is not None:
        dates_to_load.append(prev_date)
    
    df_selected = df_weights[df_weights["date"].isin(dates_to_load)].copy()
    
    return df_selected, target_date_pd, prev_date


def get_stock_returns_around_date(target_date: pd.Timestamp, symbols: list, days_before: int = 3, days_after: int = 3) -> pd.DataFrame:
    """
    指定日周辺の銘柄リターンを取得
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    symbols : list
        銘柄リスト
    days_before : int
        前後の営業日数（デフォルト: 3）
    days_after : int
        前後の営業日数（デフォルト: 3）
    
    Returns
    -------
    pd.DataFrame
        trade_date, symbol, close, ret_cc を含むDataFrame
    """
    # 価格データを一括読み込み（data_loader.load_prices()を使用）
    print(f"  [INFO] 価格データを読み込み中（{len(symbols)}銘柄）...")
    try:
        df_prices_all = data_loader.load_prices()
        if df_prices_all is None or len(df_prices_all) == 0:
            raise ValueError("価格データが取得できませんでした")
        
        # 日付カラム名を確認
        date_col = "date" if "date" in df_prices_all.columns else "trade_date"
        if date_col not in df_prices_all.columns:
            raise ValueError(f"日付カラムが見つかりません: {df_prices_all.columns.tolist()}")
        
        df_prices_all[date_col] = pd.to_datetime(df_prices_all[date_col])
        
        # 指定銘柄のみをフィルタ
        if "symbol" in df_prices_all.columns:
            df_prices = df_prices_all[df_prices_all["symbol"].isin(symbols)].copy()
        else:
            raise ValueError("symbol列が見つかりません")
        
        # 日付でフィルタ（周辺日）
        date_start = target_date - pd.Timedelta(days=days_before * 2)  # 余裕を持って
        date_end = target_date + pd.Timedelta(days=days_after * 2)
        
        df_prices = df_prices[
            (df_prices[date_col] >= date_start) & 
            (df_prices[date_col] <= date_end)
        ].copy()
        
        # リターンを計算（close-to-close）
        if "close" not in df_prices.columns:
            raise ValueError("close列が見つかりません")
        
        df_prices = df_prices.sort_values(["symbol", date_col])
        df_prices["ret_cc"] = df_prices.groupby("symbol")["close"].pct_change()
        
        # カラム名を統一（trade_date）
        if date_col != "trade_date":
            df_prices = df_prices.rename(columns={date_col: "trade_date"})
        
        # 欠損銘柄を確認
        loaded_symbols = df_prices["symbol"].unique()
        missing_symbols = set(symbols) - set(loaded_symbols)
        if len(missing_symbols) > 0:
            print(f"  [WARN] {len(missing_symbols)}個の銘柄で価格データが取得できませんでした: {list(missing_symbols)[:10]}")
        
        return df_prices
        
    except Exception as e:
        print(f"  [ERROR] 価格データ読み込みエラー: {e}")
        import traceback
        traceback.print_exc()
        raise


def analyze_attribution(
    target_date: pd.Timestamp,
    weights_path: Path,
    strategy: str,
    window: int = None,
    return_threshold: float = 0.15
) -> pd.DataFrame:
    """
    指定日の銘柄別寄与を分析
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    weights_path : Path
        weightsファイルのパス
    strategy : str
        戦略名
    window : int, optional
        ウィンドウサイズ
    return_threshold : float
        異常リターンの閾値（デフォルト: 0.15 = 15%）
    
    Returns
    -------
    pd.DataFrame
        銘柄別寄与テーブル
    """
    # weightsを読み込む（当日と前日）
    df_weights, target_date_pd, prev_date = load_weights_for_date(weights_path, target_date)
    
    # 対象日のweights
    weights_t = df_weights[df_weights["date"] == target_date_pd].set_index("symbol")["weight"]
    
    # 前日のweights（あれば）
    if prev_date is not None:
        weights_t_1 = df_weights[df_weights["date"] == prev_date].set_index("symbol")["weight"]
    else:
        weights_t_1 = pd.Series(dtype=float)
    
    # 銘柄リストを取得
    symbols = weights_t.index.tolist()
    
    # リターンを取得（周辺日を含む）
    df_returns = get_stock_returns_around_date(target_date_pd, symbols, days_before=3, days_after=3)
    
    # 対象日のリターンを抽出
    target_returns = df_returns[df_returns["trade_date"] == target_date_pd].set_index("symbol")["ret_cc"]
    
    # 前営業日を取得
    prev_trade_date = None
    prev_returns = pd.Series(dtype=float)
    prev2_trade_date = None
    prev2_returns = pd.Series(dtype=float)
    
    dates_before_target = sorted(df_returns[df_returns["trade_date"] < target_date_pd]["trade_date"].unique())
    if len(dates_before_target) > 0:
        prev_trade_date = pd.to_datetime(max(dates_before_target))
        prev_returns = df_returns[df_returns["trade_date"] == prev_trade_date].set_index("symbol")["ret_cc"]
        
        # さらに前の営業日
        dates_before_prev = sorted(df_returns[df_returns["trade_date"] < prev_trade_date]["trade_date"].unique())
        if len(dates_before_prev) > 0:
            prev2_trade_date = pd.to_datetime(max(dates_before_prev))
            prev2_returns = df_returns[df_returns["trade_date"] == prev2_trade_date].set_index("symbol")["ret_cc"]
    
    # 日数差を計算
    if prev_trade_date is not None:
        days_gap = (target_date_pd - prev_trade_date).days
    else:
        days_gap = None
    
    # 銘柄別テーブルを構築
    result_rows = []
    for symbol in symbols:
        ret_D = target_returns.get(symbol, np.nan)
        ret_Dprev = prev_returns.get(symbol, np.nan) if prev_trade_date is not None else np.nan
        ret_Dprev2 = prev2_returns.get(symbol, np.nan) if prev2_trade_date is not None else np.nan
        
        weight_t = weights_t.get(symbol, 0.0)
        weight_t_1 = weights_t_1.get(symbol, 0.0) if prev_date is not None else 0.0
        
        contribution_t = weight_t * ret_D if not np.isnan(ret_D) else np.nan
        contribution_t_1 = weight_t_1 * ret_D if not np.isnan(ret_D) else np.nan
        
        # 異常リターンフラグ
        abnormal_ret = abs(ret_D) > return_threshold if not np.isnan(ret_D) else False
        
        # 2日分合算疑い（ret_D が ret_Dprev + ret_Dprev2 の合算に近いか）
        suspect_2day_sum = False
        if not np.isnan(ret_D) and not np.isnan(ret_Dprev) and not np.isnan(ret_Dprev2):
            # 2日分の複利リターン
            expected_2day_compound = (1.0 + ret_Dprev2) * (1.0 + ret_Dprev) - 1.0
            # 単純合計
            expected_2day_sum = ret_Dprev2 + ret_Dprev
            # ret_Dが2日分の合算に近いか（複利または単純合計のどちらかに近い）
            if abs(ret_D - expected_2day_compound) < 0.01 or abs(ret_D - expected_2day_sum) < 0.01:
                suspect_2day_sum = True
        
        result_rows.append({
            "symbol": symbol,
            "return_on_D": ret_D,
            "return_Dprev": ret_Dprev,
            "return_Dprev2": ret_Dprev2,
            "weight_t": weight_t,
            "weight_t_1": weight_t_1,
            "contribution_t": contribution_t,
            "contribution_t_1": contribution_t_1,
            "abnormal_ret": abnormal_ret,
            "suspect_2day_sum": suspect_2day_sum,
            "days_gap": days_gap,
        })
    
    df_attribution = pd.DataFrame(result_rows)
    
    # 追加情報を追加
    df_attribution["target_date"] = target_date_pd
    df_attribution["prev_trade_date"] = prev_trade_date
    df_attribution["prev2_trade_date"] = prev2_trade_date
    
    return df_attribution


def print_attribution_summary(df_attribution: pd.DataFrame, target_date: pd.Timestamp):
    """
    寄与分析結果を表示
    
    Parameters
    ----------
    df_attribution : pd.DataFrame
        銘柄別寄与テーブル
    target_date : pd.Timestamp
        対象日
    """
    print("=" * 80)
    print(f"【銘柄別寄与分析: {target_date.date()}】")
    print("=" * 80)
    
    # 集計値
    sum_contrib_t = df_attribution["contribution_t"].sum()
    sum_contrib_t_1 = df_attribution["contribution_t_1"].sum()
    
    print(f"\n【集計】")
    print(f"  sum(contribution_t)   = {sum_contrib_t:.8f}")
    print(f"  sum(contribution_t_1) = {sum_contrib_t_1:.8f}")
    print(f"  （期待値はweights版の日次リターンに近いはず）")
    
    # 日数ギャップ
    days_gap = df_attribution["days_gap"].iloc[0] if "days_gap" in df_attribution.columns else None
    if days_gap is not None and days_gap > 3:
        print(f"\n  ⚠ 祝日ギャップ疑い: {days_gap}日間隔（前営業日との間）")
    
    # 異常リターンの数
    abnormal_count = df_attribution["abnormal_ret"].sum()
    if abnormal_count > 0:
        print(f"\n  ⚠ 異常リターン（>{df_attribution['return_on_D'].abs().quantile(0.95):.2%}）: {abnormal_count}銘柄")
    
    # return絶対値の大きい順 Top20
    print(f"\n【return絶対値の大きい順 Top20】")
    df_attribution_sorted = df_attribution.copy()
    df_attribution_sorted["abs_return"] = df_attribution_sorted["return_on_D"].abs()
    df_return_top = df_attribution_sorted.nlargest(20, "abs_return", keep="all").copy()
    df_return_top = df_return_top.sort_values("abs_return", ascending=False)
    display_cols = ["symbol", "return_on_D", "weight_t", "weight_t_1", "contribution_t", "contribution_t_1", "abnormal_ret"]
    print(df_return_top[display_cols].to_string(index=False, float_format="%.6f"))
    
    # contribution絶対値の大きい順 Top20（weight_t版）
    print(f"\n【contribution絶対値の大きい順 Top20（weight_t使用）】")
    df_attribution_sorted["abs_contrib_t"] = df_attribution_sorted["contribution_t"].abs()
    df_contrib_top = df_attribution_sorted.nlargest(20, "abs_contrib_t", keep="all").copy()
    df_contrib_top = df_contrib_top.sort_values("abs_contrib_t", ascending=False)
    print(df_contrib_top[display_cols].to_string(index=False, float_format="%.6f"))
    
    # contribution絶対値の大きい順 Top20（weight_t_1版）
    print(f"\n【contribution絶対値の大きい順 Top20（weight_t_1使用）】")
    df_attribution_sorted["abs_contrib_t_1"] = df_attribution_sorted["contribution_t_1"].abs()
    df_contrib_top_1 = df_attribution_sorted.nlargest(20, "abs_contrib_t_1", keep="all").copy()
    df_contrib_top_1 = df_contrib_top_1.sort_values("abs_contrib_t_1", ascending=False)
    print(df_contrib_top_1[display_cols].to_string(index=False, float_format="%.6f"))


def check_surrounding_days(target_date: pd.Timestamp, df_returns_comparison: pd.DataFrame, days_range: int = 3):
    """
    周辺日のログを表示
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    df_returns_comparison : pd.DataFrame
        比較結果DataFrame
    days_range : int
        前後の範囲（デフォルト: 3）
    """
    print(f"\n【周辺日のログ（{target_date.date()} ±{days_range}営業日）】")
    print("=" * 80)
    
    target_date_pd = pd.to_datetime(target_date).normalize()
    
    # 周辺日の範囲を取得
    all_dates = sorted(df_returns_comparison["trade_date"].unique())
    target_idx = None
    for i, date in enumerate(all_dates):
        if pd.to_datetime(date).normalize() == target_date_pd:
            target_idx = i
            break
    
    if target_idx is None:
        print(f"  対象日が見つかりません")
        return
    
    # 周辺日のインデックス範囲
    start_idx = max(0, target_idx - days_range)
    end_idx = min(len(all_dates), target_idx + days_range + 1)
    
    df_surrounding = df_returns_comparison[
        df_returns_comparison["trade_date"].isin(all_dates[start_idx:end_idx])
    ].copy()
    
    df_surrounding = df_surrounding.sort_values("trade_date")
    df_surrounding["date_str"] = df_surrounding["trade_date"].dt.strftime("%Y-%m-%d")
    
    display_cols = ["date_str", "port_ret_cc_weights", "port_ret_cc_eval", "diff", "abs_diff"]
    print(df_surrounding[display_cols].to_string(index=False, float_format="%.6f"))


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="STOP付cross4の差分が最大の日について銘柄別寄与を分析"
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
        help="分析対象日（YYYY-MM-DD形式）。指定しない場合は差分最大日を自動特定"
    )
    parser.add_argument(
        "--return-threshold",
        type=float,
        default=0.15,
        help="異常リターンの閾値（デフォルト: 0.15 = 15%）"
    )
    
    args = parser.parse_args()
    
    if args.strategy != "baseline" and args.window is None:
        parser.error("--window は baseline以外では必須です")
    
    print("=" * 80)
    print(f"=== 銘柄別寄与分析（差分日デバッグ） ===")
    print("=" * 80)
    
    # window_strを定義
    if args.window is not None:
        window_str = f"w{args.window}"
        print(f"\n戦略: {args.strategy}")
        print(f"Window: {args.window}")
    else:
        window_str = "baseline"
        print(f"\n戦略: {args.strategy}")
    print(f"異常リターン閾値: {args.return_threshold:.2%}")
    
    # returns比較を読み込む
    print(f"\n[STEP 1] returns比較データを読み込み中...")
    try:
        df_comparison = load_returns_comparison(args.strategy, args.window)
        print(f"  ✓ {len(df_comparison)} 日分")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 対象日を決定
    if args.date is not None:
        target_date = pd.to_datetime(args.date)
        print(f"\n[STEP 2] 指定日を使用: {target_date.date()}")
    else:
        target_date = find_max_diff_date(df_comparison)
        max_diff = df_comparison[df_comparison["trade_date"] == target_date]["abs_diff"].iloc[0]
        print(f"\n[STEP 2] 差分最大日を自動特定: {target_date.date()}")
        print(f"  最大差分: {max_diff:.8f}")
        print(f"  weights版リターン: {df_comparison[df_comparison['trade_date'] == target_date]['port_ret_cc_weights'].iloc[0]:.8f}")
        print(f"  eval版リターン: {df_comparison[df_comparison['trade_date'] == target_date]['port_ret_cc_eval'].iloc[0]:.8f}")
    
    # weightsファイルのパス
    if args.strategy == "baseline":
        weights_path = WEIGHTS_DIR / "cross4_target_weights.parquet"
    else:
        weights_path = WEIGHTS_DIR / f"cross4_target_weights_{args.strategy}_w{args.window}.parquet"
    
    if not weights_path.exists():
        print(f"  ✗ weightsファイルが見つかりません: {weights_path}")
        return 1
    
    # 銘柄別寄与を分析
    print(f"\n[STEP 3] 銘柄別寄与を分析中...")
    try:
        df_attribution = analyze_attribution(
            target_date,
            weights_path,
            args.strategy,
            args.window,
            return_threshold=args.return_threshold
        )
        print(f"  ✓ {len(df_attribution)} 銘柄")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 結果を表示
    print_attribution_summary(df_attribution, target_date)
    
    # 周辺日のログ
    check_surrounding_days(target_date, df_comparison, days_range=3)
    
    # 結果をCSVに保存
    output_path = RESEARCH_REPORTS_DIR / f"diff_day_attribution_{args.strategy}_{window_str}_{target_date.strftime('%Y%m%d')}.csv"
    df_attribution.to_csv(output_path, index=False)
    print(f"\n✓ 結果を保存: {output_path}")
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

