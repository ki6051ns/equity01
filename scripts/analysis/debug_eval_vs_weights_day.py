#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/debug_eval_vs_weights_day.py

eval_stop_regimes.py と backtest_from_weights_with_stop.py の差分を特定日について詳細分析

機能:
- 指定日±数日のポートフォリオリターンを比較
- 差分の原因を分解（日付アライン、STOPフラグ不一致、欠損埋め等）
- Top寄与銘柄を表示（weights側のみ）
"""

import sys
import io
import os
from pathlib import Path
from datetime import datetime

# Windows環境での文字化け対策
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# ログファイル出力用のクラス
class TeeOutput:
    """標準出力をコンソールとファイルの両方に出力する"""
    def __init__(self, *files):
        self.files = files
    
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    
    def flush(self):
        for f in self.files:
            f.flush()

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


def rebuild_contributions_from_weights_file(
    weights_path: Path,
    use_adj_close: bool = True,
    use_weight_lag: bool = True
):
    """
    weightsファイル + prices から寄与を再構築（rebuild_port_ret_from_weights()と同様のロジック）
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス（cross4_target_weights_{strategy}_w{window}.parquet等）
    use_adj_close : bool
        Trueならadj_close、Falseならcloseを使用
    use_weight_lag : bool
        Trueなら w[t-1] * r[t]（正）、Falseなら w[t] * r[t]（look-ahead）
    
    Returns
    -------
    dict with keys:
        port_ret : pd.Series
            trade_dateをindexとするポートフォリオリターン
        contrib_df : pd.DataFrame
            index=trade_date, columns=symbol の寄与行列
        ret_df : pd.DataFrame
            index=trade_date, columns=symbol の銘柄リターン行列
        w_used_df : pd.DataFrame
            index=trade_date, columns=symbol の適用ウェイト行列
    """
    if not weights_path.exists():
        raise FileNotFoundError(f"weightsファイルが見つかりません: {weights_path}")
    
    df_weights = pd.read_parquet(weights_path)
    
    # 日付カラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df_weights.columns:
            date_col = col
            break
    
    if date_col is None:
        raise KeyError(f"日付カラムが見つかりません: {df_weights.columns.tolist()}")
    
    df_weights[date_col] = pd.to_datetime(df_weights[date_col])
    
    # 必須カラムを確認
    required_cols = ["symbol", "weight"]
    missing_cols = [col for col in required_cols if col not in df_weights.columns]
    if missing_cols:
        raise KeyError(f"必須カラムが不足しています: {missing_cols}")
    
    # 価格データを読み込む
    df_prices_all = data_loader.load_prices()
    if df_prices_all is None or len(df_prices_all) == 0:
        raise ValueError("価格データが取得できませんでした")
    
    # 日付カラムを確認
    price_date_col = "date" if "date" in df_prices_all.columns else "trade_date"
    if price_date_col not in df_prices_all.columns:
        raise ValueError(f"価格データの日付カラムが見つかりません: {df_prices_all.columns.tolist()}")
    
    df_prices_all[price_date_col] = pd.to_datetime(df_prices_all[price_date_col])
    
    # 価格カラムを選択
    if use_adj_close and "adj_close" in df_prices_all.columns:
        price_col = "adj_close"
    elif "close" in df_prices_all.columns:
        price_col = "close"
    else:
        raise ValueError("価格カラム（adj_close/close）が見つかりません")
    
    # 銘柄リストを取得
    symbols = sorted(df_weights["symbol"].unique().tolist())
    
    # 価格データをフィルタ
    df_prices = df_prices_all[df_prices_all["symbol"].isin(symbols)].copy()
    
    # リターンを計算（close-to-close）
    df_prices = df_prices.sort_values(["symbol", price_date_col])
    df_prices["ret_cc"] = df_prices.groupby("symbol")[price_col].pct_change()
    
    # 日付範囲を取得
    dates = sorted(df_weights[date_col].unique())
    
    # 各日についてポートフォリオリターンを計算
    port_ret_list = []
    contrib_dict = {}  # {date: {symbol: contrib}}
    ret_dict = {}  # {date: {symbol: ret}}
    w_used_dict = {}  # {date: {symbol: weight}}
    
    for i, date in enumerate(dates):
        date_pd = pd.to_datetime(date).normalize()
        
        # weightsを取得
        if use_weight_lag and i > 0:
            # w[t-1]を使用（正）
            prev_date = pd.to_datetime(dates[i-1]).normalize()
            weights_day = df_weights[df_weights[date_col] == prev_date].copy()
        else:
            # w[t]を使用（look-aheadの可能性）
            weights_day = df_weights[df_weights[date_col] == date_pd].copy()
        
        if weights_day.empty:
            continue
        
        weights_series = weights_day.set_index("symbol")["weight"]
        
        # 当日のリターンを取得（r[t]）
        prices_day = df_prices[df_prices[price_date_col] == date_pd].copy()
        if prices_day.empty:
            continue
        
        rets_series = prices_day.set_index("symbol")["ret_cc"]
        
        # ポートフォリオリターンを計算: Σ w * r
        common_symbols = weights_series.index.intersection(rets_series.index)
        if len(common_symbols) == 0:
            continue
        
        weights_aligned = weights_series.loc[common_symbols]
        rets_aligned = rets_series.loc[common_symbols]
        
        # 欠損値を0で埋める（デフォルト）
        weights_aligned = weights_aligned.fillna(0.0)
        rets_aligned = rets_aligned.fillna(0.0)
        
        # 寄与を計算: contrib[t, i] = w_used[t, i] * ret[t, i]
        contrib = weights_aligned * rets_aligned
        port_ret = contrib.sum()
        
        port_ret_list.append({
            "trade_date": date_pd,
            "port_ret_cc": port_ret,
        })
        
        # 寄与、リターン、ウェイトを保存
        contrib_dict[date_pd] = contrib.to_dict()
        ret_dict[date_pd] = rets_aligned.to_dict()
        w_used_dict[date_pd] = weights_aligned.to_dict()
    
    df_result = pd.DataFrame(port_ret_list)
    if len(df_result) == 0:
        raise ValueError("ポートフォリオリターンが計算できませんでした")
    
    port_ret_series = df_result.set_index("trade_date")["port_ret_cc"].sort_index()
    
    # DataFrameに変換
    contrib_df = pd.DataFrame(contrib_dict).T  # index=date, columns=symbol
    contrib_df = contrib_df.sort_index()
    ret_df = pd.DataFrame(ret_dict).T
    ret_df = ret_df.sort_index()
    w_used_df = pd.DataFrame(w_used_dict).T
    w_used_df = w_used_df.sort_index()
    
    return {
        "port_ret": port_ret_series,
        "contrib_df": contrib_df,
        "ret_df": ret_df,
        "w_used_df": w_used_df,
    }


def load_eval_results(strategy: str, window: int) -> pd.DataFrame:
    """
    eval_stop_regimes.pyの結果を読み込む
    """
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
    
    # 戦略カラムを特定
    if strategy == "baseline":
        strategy_col = "baseline"
    else:
        strategy_col = f"{strategy}_{window}"
    
    if strategy_col not in df.columns:
        raise KeyError(f"戦略カラム '{strategy_col}' が見つかりません。利用可能な列: {df.columns.tolist()}")
    
    result_df = pd.DataFrame({
        "trade_date": df[date_col],
        "port_ret_cc_eval": df[strategy_col],
    })
    
    result_df = result_df.dropna().sort_values("trade_date").reset_index(drop=True)
    
    return result_df


def load_weights_results(strategy: str, window: int) -> pd.DataFrame:
    """
    backtest_from_weights_with_stop.pyの結果を読み込む
    """
    weights_path = WEIGHTS_BT_DIR / f"cross4_from_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        raise FileNotFoundError(f"backtest_from_weights_with_stop.pyの出力ファイルが見つかりません: {weights_path}")
    
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
    
    result_df = pd.DataFrame({
        "trade_date": df[date_col],
        "port_ret_cc_weights": df["port_ret_cc"],
    })
    
    result_df = result_df.dropna().sort_values("trade_date").reset_index(drop=True)
    
    return result_df


def compute_stop_flag(port_ret: pd.Series, tpx_ret: pd.Series, window: int) -> pd.Series:
    """
    STOP条件を計算（eval_stop_regimes.py準拠）
    """
    alpha = port_ret - tpx_ret
    
    # ルックアヘッドバイアス回避: 前日までの情報を使うため .shift(1)
    roll_alpha = alpha.rolling(window=window, min_periods=1).sum().shift(1)
    roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1)
    
    # NaNをFalseで埋める
    roll_alpha = roll_alpha.fillna(False)
    roll_tpx = roll_tpx.fillna(False)
    
    # stop_cond = True の時は「STOP期間中」
    stop_cond = (roll_alpha < 0) & (roll_tpx < 0)
    
    return stop_cond


def load_eval_weights_for_date(target_date: pd.Timestamp, use_weight_lag: bool = True) -> pd.DataFrame:
    """
    eval側が使用したweightsを取得（daily_portfolio_guardedから）
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    use_weight_lag : bool
        Trueならw[t-1]、Falseならw[t]を使用
    
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
    
    # 日付範囲を取得
    date_range = sorted(df[date_col].unique())
    
    # 対象日のweightsを取得
    if use_weight_lag:
        # w[t-1]を使用（eval側のデフォルト）
        prev_trading_date = None
        for d in reversed(date_range):
            if d < target_date:
                prev_trading_date = d
                break
        
        if prev_trading_date is None:
            return pd.DataFrame(columns=["date", "symbol", "weight"])
        
        weights_day = df[df[date_col] == prev_trading_date].copy()
    else:
        # w[t]を使用（比較用）
        weights_day = df[df[date_col] == target_date].copy()
    
    return weights_day[["date", "symbol", "weight"]]


def calculate_eval_returns(target_date: pd.Timestamp, use_adj_close: bool = True) -> pd.Series:
    """
    eval側が使用したreturnsを計算
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    use_adj_close : bool
        Trueならadj_close、Falseならcloseを使用
    
    Returns
    -------
    pd.Series
        symbolをindexとするリターンSeries
    """
    prices_df = data_loader.load_prices()
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    
    # 前営業日を取得
    date_range = sorted(prices_df["date"].unique())
    prev_trading_date = None
    for d in reversed(date_range):
        if d < target_date:
            prev_trading_date = d
            break
    
    if prev_trading_date is None:
        return pd.Series(dtype=float)
    
    # 前営業日と当日の価格を取得
    prices_prev = prices_df[prices_df["date"] == prev_trading_date].copy()
    prices_target = prices_df[prices_df["date"] == target_date].copy()
    
    if len(prices_prev) == 0 or len(prices_target) == 0:
        return pd.Series(dtype=float)
    
    # 価格カラムを選択
    price_col = "adj_close" if (use_adj_close and "adj_close" in prices_df.columns) else "close"
    
    prices_prev = prices_prev.set_index("symbol")[[price_col]]
    prices_target = prices_target.set_index("symbol")[[price_col]]
    
    # リターンを計算: r[t] = price[t] / price[t-1] - 1
    common_symbols = prices_prev.index.intersection(prices_target.index)
    if len(common_symbols) == 0:
        return pd.Series(dtype=float)
    
    prices_prev_aligned = prices_prev.loc[common_symbols, price_col]
    prices_target_aligned = prices_target.loc[common_symbols, price_col]
    rets = (prices_target_aligned / prices_prev_aligned - 1.0)
    
    # 欠損を0で埋める（デフォルト）
    rets = rets.fillna(0.0)
    
    return rets


def calculate_eval_contributions(
    target_date: pd.Timestamp,
    use_weight_lag: bool = True,
    use_adj_close: bool = True,
    na_fill: str = "zero"
) -> pd.DataFrame:
    """
    eval側の銘柄寄与を計算
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    use_weight_lag : bool
        Trueならw[t-1]、Falseならw[t]を使用
    use_adj_close : bool
        Trueならadj_close、Falseならcloseを使用
    na_fill : str
        欠損の埋め方（"zero"または"drop"）
    
    Returns
    -------
    pd.DataFrame
        symbol, weight, ret, contribution, contribution_abs を含むDataFrame
    """
    # weightsを取得
    weights_day = load_eval_weights_for_date(target_date, use_weight_lag=use_weight_lag)
    
    if len(weights_day) == 0:
        return pd.DataFrame()
    
    # returnsを取得
    rets = calculate_eval_returns(target_date, use_adj_close=use_adj_close)
    
    if len(rets) == 0:
        return pd.DataFrame()
    
    # weightsとreturnsをマージ
    weights_series = weights_day.set_index("symbol")["weight"].astype(str).astype(float)
    rets_series = rets.astype(str).astype(float)
    
    # intersectionを取得
    common_symbols = weights_series.index.intersection(rets_series.index)
    
    if len(common_symbols) == 0:
        return pd.DataFrame()
    
    weights_aligned = weights_series.loc[common_symbols]
    rets_aligned = rets_series.loc[common_symbols]
    
    # 欠損処理
    if na_fill == "zero":
        weights_aligned = weights_aligned.fillna(0.0)
        rets_aligned = rets_aligned.fillna(0.0)
    elif na_fill == "drop":
        mask = weights_aligned.notna() & rets_aligned.notna()
        weights_aligned = weights_aligned[mask]
        rets_aligned = rets_aligned[mask]
        if len(weights_aligned) == 0:
            return pd.DataFrame()
    
    # 寄与を計算
    contributions = weights_aligned * rets_aligned
    
    result_df = pd.DataFrame({
        "symbol": contributions.index,
        "weight": weights_aligned.values,
        "ret": rets_aligned.values,
        "contribution": contributions.values,
        "contribution_abs": contributions.abs().values
    })
    
    return result_df.sort_values("contribution_abs", ascending=False)


def load_weights_for_date(strategy: str, window: int, target_date: pd.Timestamp) -> pd.DataFrame:
    """
    指定日のweightsを読み込む
    """
    weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        raise FileNotFoundError(f"weightsファイルが見つかりません: {weights_path}")
    
    df = pd.read_parquet(weights_path)
    df["date"] = pd.to_datetime(df["date"])
    
    # 前日を取得（w[t-1]を使用するため）
    prev_date = target_date - pd.Timedelta(days=1)
    
    # 前日のweightsを取得（存在しない場合は前営業日を探す）
    date_range = df["date"].unique()
    date_range = sorted(date_range)
    
    # target_dateの前営業日を探す
    prev_trading_date = None
    for d in reversed(date_range):
        if d < target_date:
            prev_trading_date = d
            break
    
    if prev_trading_date is None:
        return pd.DataFrame(columns=["date", "symbol", "weight"])
    
    weights_day = df[df["date"] == prev_trading_date].copy()
    
    return weights_day[["date", "symbol", "weight"]]


def analyze_date_difference(
    strategy: str,
    window: int,
    target_date_str: str,
    n_prev: int = 3,
    n_next: int = 3,
    output_file: str = None
):
    """
    指定日について差分を詳細分析
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    target_date_str : str
        対象日（YYYY-MM-DD）
    n_prev : int
        対象日の前日数
    n_next : int
        対象日の後日数
    output_file : str, optional
        出力ファイルパス（指定しない場合は出力しない）
    """
    target_date = pd.to_datetime(target_date_str)
    
    # ファイル出力を設定
    original_stdout = sys.stdout
    log_file = None
    
    if output_file:
        log_file_path = Path(output_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_file_path, 'w', encoding='utf-8')
        sys.stdout = TeeOutput(original_stdout, log_file)
    
    try:
        print("=" * 80)
        print(f"=== 差分分析: {strategy.upper()} (window={window}), 対象日={target_date.date()} ===")
        print("=" * 80)
        
        # データ読み込み
        print(f"\n[STEP 1] データを読み込み中...")
        eval_df = load_eval_results(strategy, window)
        weights_df = load_weights_results(strategy, window)
        
        print(f"  eval側: {len(eval_df)} 日分")
        print(f"  weights側: {len(weights_df)} 日分")
        
        # TOPIXリターンを読み込む
        tpx_path = DATA_DIR / "index_tpx_daily.parquet"
        if not tpx_path.exists():
            print(f"  [WARN] TOPIXリターンファイルが見つかりません: {tpx_path}")
            tpx_ret = None
        else:
            df_tpx = pd.read_parquet(tpx_path)
            date_col = "trade_date" if "trade_date" in df_tpx.columns else "date"
            df_tpx[date_col] = pd.to_datetime(df_tpx[date_col])
            df_tpx = df_tpx.set_index(date_col).sort_index()
            if "tpx_ret_cc" in df_tpx.columns:
                tpx_ret = df_tpx["tpx_ret_cc"]
            else:
                tpx_ret = None
        
        # cross4 returnsを読み込む（STOPフラグ計算用）
        try:
            from scripts.analysis.build_cross4_target_weights_with_stop import load_cross4_returns_for_stop
            df_returns_for_stop = load_cross4_returns_for_stop()
            df_returns_for_stop = df_returns_for_stop.sort_values("trade_date").reset_index(drop=True)
            port_ret_for_stop = df_returns_for_stop.set_index("trade_date")["port_ret_cc"]
            tpx_ret_for_stop = df_returns_for_stop.set_index("trade_date")["tpx_ret_cc"]
            
            # STOPフラグを計算
            stop_flag = compute_stop_flag(port_ret_for_stop, tpx_ret_for_stop, window)
        except Exception as e:
            print(f"  [WARN] STOPフラグ計算エラー: {e}")
            stop_flag = None
        
        # 日付範囲を決定
        all_dates = sorted(set(eval_df["trade_date"].tolist() + weights_df["trade_date"].tolist()))
        target_idx = None
        for i, d in enumerate(all_dates):
            if d >= target_date:
                target_idx = i
                break
        
        if target_idx is None:
            print(f"  [ERROR] 対象日 {target_date.date()} が見つかりません")
            return
        
        # 対象日±n日を取得
        start_idx = max(0, target_idx - n_prev)
        end_idx = min(len(all_dates), target_idx + n_next + 1)
        date_range = all_dates[start_idx:end_idx]
        
        print(f"\n[STEP 2] 対象日±{n_prev}日を分析中...")
        print(f"  日付範囲: {date_range[0].date()} ～ {date_range[-1].date()}")
        
        # マージ
        merged = pd.merge(
            eval_df,
            weights_df,
            on="trade_date",
            how="outer",
            suffixes=("_eval", "_weights")
        )
        merged = merged[merged["trade_date"].isin(date_range)].sort_values("trade_date").reset_index(drop=True)
        
        # TOPIXリターンを追加
        if tpx_ret is not None:
            merged = merged.set_index("trade_date")
            merged["tpx_ret"] = tpx_ret
            merged = merged.reset_index()
            merged["tpx_ret"] = merged["tpx_ret"].fillna(0.0)
        else:
            merged["tpx_ret"] = 0.0
        
        # STOPフラグを追加
        if stop_flag is not None:
            merged = merged.set_index("trade_date")
            merged["stop_flag"] = stop_flag
            merged = merged.reset_index()
            merged["stop_flag"] = merged["stop_flag"].fillna(False)
        else:
            merged["stop_flag"] = False
        
        # 差分を計算
        merged["abs_diff"] = (merged["port_ret_cc_eval"] - merged["port_ret_cc_weights"]).abs()
        
        # 表示
        print(f"\n[結果] 対象日±{n_prev}日の比較")
        print("=" * 80)
        display_cols = ["trade_date", "port_ret_cc_eval", "port_ret_cc_weights", "abs_diff", "stop_flag", "tpx_ret"]
        display_df = merged[display_cols].copy()
        display_df["trade_date"] = display_df["trade_date"].dt.date
        display_df["port_ret_cc_eval"] = display_df["port_ret_cc_eval"].fillna(np.nan)
        display_df["port_ret_cc_weights"] = display_df["port_ret_cc_weights"].fillna(np.nan)
        print(display_df.to_string(index=False, float_format="%.8f"))
        
        # 対象日の詳細分析
        target_row = merged[merged["trade_date"] == target_date]
        if len(target_row) > 0:
            print(f"\n[STEP 3] 対象日 {target_date.date()} の詳細分析")
            print("=" * 80)
            
            target_row = target_row.iloc[0]
            port_ret_eval = target_row["port_ret_cc_eval"]
            port_ret_weights = target_row["port_ret_cc_weights"]
            diff = port_ret_eval - port_ret_weights
            
            print(f"  port_ret_cc_eval:    {port_ret_eval:.10f}")
            print(f"  port_ret_cc_weights: {port_ret_weights:.10f}")
            print(f"  差分:                 {diff:.10f}")
            print(f"  STOPフラグ:          {target_row['stop_flag']}")
            
            # weights側の寄与は後でrebuild_contributions_from_weights_file()で計算（STEP 4で統一的に処理）
            
            # eval側の銘柄寄与を計算（rebuild_port_ret_from_weights()を使用）
            print(f"\n[eval側] ポートフォリオリターンの内訳（rebuild_port_ret_from_weights()から取得）")
            print("-" * 80)
            
            try:
                from scripts.analysis.rebuild_port_ret_from_weights import rebuild_port_ret_from_weights
                
                # eval側はdaily_portfolio_guardedからrebuild
                eval_rebuild_result = rebuild_port_ret_from_weights(
                    use_adj_close=True,  # eval側はadj_closeを使用
                    use_weight_lag=True  # eval側はw[t-1]を使用
                )
                
                eval_port_ret = eval_rebuild_result["port_ret"]
                eval_contrib_df = eval_rebuild_result["contrib_df"]
                eval_ret_df = eval_rebuild_result["ret_df"]
                eval_w_used_df = eval_rebuild_result["w_used_df"]
                
                # 対象日の寄与を取得
                if target_date in eval_contrib_df.index:
                    eval_contrib_date = eval_contrib_df.loc[target_date].dropna()
                    eval_ret_date = eval_ret_df.loc[target_date].dropna()
                    eval_w_used_date = eval_w_used_df.loc[target_date].dropna()
                    
                    # DataFrameにまとめる
                    eval_contributions = pd.DataFrame({
                        "symbol": eval_contrib_date.index,
                        "weight": eval_w_used_date.values,
                        "ret": eval_ret_date.values,
                        "contribution": eval_contrib_date.values,
                        "contribution_abs": eval_contrib_date.abs().values
                    })
                    
                    print("  [設定] w[t-1], adj_close (rebuild_port_ret_from_weights()使用)")
                    print("  Top10寄与銘柄（w[t-1] * r[t], adj_close）:")
                    top10 = eval_contributions.nlargest(10, "contribution_abs")
                    display_cols = ["symbol", "weight", "ret", "contribution"]
                    print(top10[display_cols].to_string(index=False, float_format="%.8f"))
                    
                    # 統計情報
                    port_ret_rebuilt = eval_contributions["contribution"].sum()
                    weights_sum = eval_contributions["weight"].sum()
                    weights_sum_pos = eval_contributions[eval_contributions["weight"] > 0]["weight"].sum()
                    weights_sum_neg = abs(eval_contributions[eval_contributions["weight"] < 0]["weight"].sum())
                    
                    print(f"\n  [統計]")
                    print(f"    合計寄与（port_ret再構築）: {port_ret_rebuilt:.10f}")
                    print(f"    eval側のport_ret: {port_ret_eval:.10f}")
                    print(f"    差分: {abs(port_ret_rebuilt - port_ret_eval):.10f}")
                    print(f"    weights合計: {weights_sum:.6f}")
                    print(f"    weights合計（ロング）: {weights_sum_pos:.6f}")
                    print(f"    weights合計（ショート）: {weights_sum_neg:.6f}")
                    print(f"    銘柄数: {len(eval_contributions)}")
                else:
                    print(f"  [WARN] 対象日 {target_date.date()} がeval側の寄与行列に存在しません")
                    eval_contributions = pd.DataFrame()
            except Exception as e:
                print(f"  [WARN] eval側の寄与計算エラー: {e}")
                import traceback
                traceback.print_exc()
                eval_contributions = pd.DataFrame()
                eval_rebuild_result = None
            
            # weights側とeval側の寄与を比較（rebuild_port_ret_from_weights()と同様のロジックを使用）
            print(f"\n[STEP 4] 寄与比較（weights側 vs eval側）")
            print("=" * 80)
            
            merged_contrib_for_cause = None  # STEP 5で使用するために初期化
            
            try:
                # weights側の寄与をrebuild
                weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
                weights_rebuild_result = rebuild_contributions_from_weights_file(
                    weights_path=weights_path,
                    use_adj_close=True,  # weights側もadj_closeを使用（統一）
                    use_weight_lag=True  # weights側もw[t-1]を使用（統一）
                )
                
                weights_port_ret = weights_rebuild_result["port_ret"]
                weights_contrib_df = weights_rebuild_result["contrib_df"]
                weights_ret_df = weights_rebuild_result["ret_df"]
                weights_w_used_df = weights_rebuild_result["w_used_df"]
                
                # 対象日の寄与を取得
                if target_date in weights_contrib_df.index:
                    weights_contrib_date = weights_contrib_df.loc[target_date].dropna()
                    weights_ret_date = weights_ret_df.loc[target_date].dropna()
                    weights_w_used_date = weights_w_used_df.loc[target_date].dropna()
                    
                    # DataFrameにまとめる
                    weights_contributions = pd.DataFrame({
                        "symbol": weights_contrib_date.index,
                        "weight": weights_w_used_date.values,
                        "ret": weights_ret_date.values,
                        "contribution": weights_contrib_date.values,
                        "contribution_abs": weights_contrib_date.abs().values
                    })
                    
                    # eval側とweights側の寄与をマージ
                    if len(eval_contributions) > 0:
                        merged_contrib = pd.merge(
                            eval_contributions[["symbol", "weight", "ret", "contribution"]].rename(columns={
                                "weight": "w_used_eval",
                                "ret": "ret_eval",
                                "contribution": "contrib_eval"
                            }),
                            weights_contributions[["symbol", "weight", "ret", "contribution"]].rename(columns={
                                "weight": "w_used_weights",
                                "ret": "ret_weights",
                                "contribution": "contrib_weights"
                            }),
                            on="symbol",
                            how="outer"
                        )
                        
                        merged_contrib["contrib_diff"] = (
                            merged_contrib["contrib_eval"].fillna(0.0) - 
                            merged_contrib["contrib_weights"].fillna(0.0)
                        )
                        merged_contrib["contrib_diff_abs"] = merged_contrib["contrib_diff"].abs()
                        
                        # 【1】日付アラインの完全可視化
                        print(f"\n  [日付アライン情報]")
                        print(f"    target_trade_date (t): {target_date.date()}")
                        
                        # eval側の日付情報を取得
                        try:
                            from scripts.analysis.rebuild_port_ret_from_weights import rebuild_port_ret_from_weights
                            eval_rebuild_for_date = rebuild_port_ret_from_weights(use_adj_close=True, use_weight_lag=True)
                            eval_port_ret_series = eval_rebuild_for_date["port_ret"]
                            
                            # target_dateの前営業日を取得（w[t-1]の場合）
                            eval_dates = sorted(eval_port_ret_series.index)
                            eval_w_date = None
                            for d in reversed(eval_dates):
                                if d < target_date:
                                    eval_w_date = d
                                    break
                            
                            if eval_w_date:
                                print(f"    eval側 w_used_date: {eval_w_date.date()} (w[t-1], t-1={eval_w_date.date()})")
                                print(f"    eval側 ret_date: {target_date.date()} (r[t], t={target_date.date()})")
                                print(f"    eval側 式表記: w[{eval_w_date.date()}] * r[{target_date.date()}] = w[t-1] * r[t]")
                        except Exception as e:
                            print(f"    [WARN] eval側の日付情報取得エラー: {e}")
                        
                        # weights側の日付情報を取得
                        try:
                            weights_path_check = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
                            weights_df_check = pd.read_parquet(weights_path_check)
                            weights_df_check["date"] = pd.to_datetime(weights_df_check["date"])
                            weights_dates = sorted(weights_df_check["date"].unique())
                            
                            weights_w_date = None
                            for d in reversed(weights_dates):
                                if d < target_date:
                                    weights_w_date = d
                                    break
                            
                            if weights_w_date:
                                print(f"    weights側 w_used_date: {weights_w_date.date()} (w[t-1], t-1={weights_w_date.date()})")
                                print(f"    weights側 ret_date: {target_date.date()} (r[t], t={target_date.date()})")
                                print(f"    weights側 式表記: w[{weights_w_date.date()}] * r[{target_date.date()}] = w[t-1] * r[t]")
                        except Exception as e:
                            print(f"    [WARN] weights側の日付情報取得エラー: {e}")
                        
                        # Δport_ret
                        print(f"\n  Δport_ret: {port_ret_eval:.10f} - {port_ret_weights:.10f} = {diff:.10f}")
                        
                        # Top10 |Δcontrib|
                        print(f"\n  Top10 |Δcontrib|（寄与差分の絶対値順）:")
                        top10_diff = merged_contrib.nlargest(10, "contrib_diff_abs")
                        print(top10_diff[["symbol", "contrib_eval", "contrib_weights", "contrib_diff"]].to_string(index=False, float_format="%.8f"))
                        
                        # Top3銘柄の詳細
                        print(f"\n  Top3銘柄の詳細比較:")
                        top3_symbols = top10_diff.head(3)["symbol"].tolist()
                        for sym in top3_symbols:
                            row = merged_contrib[merged_contrib["symbol"] == sym].iloc[0]
                            print(f"\n    [{sym}]")
                            print(f"      w_used_eval:    {row['w_used_eval']:.8f}")
                            print(f"      w_used_weights: {row['w_used_weights']:.8f}")
                            print(f"      ret_eval:       {row['ret_eval']:.8f}")
                            print(f"      ret_weights:    {row['ret_weights']:.8f}")
                            print(f"      contrib_eval:   {row['contrib_eval']:.8f}")
                            print(f"      contrib_weights: {row['contrib_weights']:.8f}")
                            print(f"      contrib_diff:   {row['contrib_diff']:.8f}")
                            print(f"      w_diff:         {row['w_used_eval'] - row['w_used_weights']:.8f}")
                            print(f"      ret_diff:       {row['ret_eval'] - row['ret_weights']:.8f}")
                        
                        # 合計差分
                        total_diff = merged_contrib["contrib_diff"].sum()
                        print(f"\n  合計寄与差分: {total_diff:.10f}")
                        
                        # 【3】価格系列差（adj_close vs close）の寄与切り分け
                        print(f"\n  [価格系列差の寄与切り分け]")
                        print("-" * 80)
                        
                        try:
                            # adj_close版とclose版を計算（日付アラインは固定：w[t-1] * r[t]）
                            weights_path_price = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
                            
                            # adj_close版
                            result_adj = rebuild_contributions_from_weights_file(
                                weights_path=weights_path_price,
                                use_adj_close=True,
                                use_weight_lag=True
                            )
                            
                            # close版
                            result_close = rebuild_contributions_from_weights_file(
                                weights_path=weights_path_price,
                                use_adj_close=False,
                                use_weight_lag=True
                            )
                            
                            if target_date in result_adj["contrib_df"].index and target_date in result_close["contrib_df"].index:
                                port_ret_adj = result_adj["port_ret"].loc[target_date]
                                port_ret_close = result_close["port_ret"].loc[target_date]
                                
                                contrib_adj_date = result_adj["contrib_df"].loc[target_date].dropna()
                                contrib_close_date = result_close["contrib_df"].loc[target_date].dropna()
                                
                                # マージして差分を計算
                                price_diff_df = pd.DataFrame({
                                    "symbol": contrib_adj_date.index,
                                    "contrib_adj": contrib_adj_date.values,
                                    "contrib_close": contrib_close_date.reindex(contrib_adj_date.index, fill_value=0.0).values
                                })
                                price_diff_df["contrib_diff"] = price_diff_df["contrib_adj"] - price_diff_df["contrib_close"]
                                price_diff_df["contrib_diff_abs"] = price_diff_df["contrib_diff"].abs()
                                price_diff_df = price_diff_df.sort_values("contrib_diff_abs", ascending=False)
                                
                                print(f"    port_ret (adj_close): {port_ret_adj:.10f}")
                                print(f"    port_ret (close):     {port_ret_close:.10f}")
                                print(f"    abs_diff(port_ret):   {abs(port_ret_adj - port_ret_close):.10f}")
                                
                                print(f"\n    Top10 |Δcontrib| (adj_close - close):")
                                print(price_diff_df.head(10)[["symbol", "contrib_adj", "contrib_close", "contrib_diff"]].to_string(index=False, float_format="%.8f"))
                                
                                total_price_diff = price_diff_df["contrib_diff"].sum()
                                print(f"\n    合計寄与差分: {total_price_diff:.10f}")
                                
                                # 原因④の判定
                                if abs(port_ret_adj - port_ret_close) > 1e-6:
                                    price_diff_ratio = abs(port_ret_adj - port_ret_close) / abs(port_ret_adj) if port_ret_adj != 0 else 0
                                    print(f"    → 原因④（price_diff）の影響: {price_diff_ratio*100:.2f}%")
                                else:
                                    print(f"    → 原因④（price_diff）の影響は軽微（< 1e-6）")
                            else:
                                print(f"    [WARN] 対象日 {target_date.date()} が価格系列比較の結果に存在しません")
                        except Exception as e:
                            print(f"    [WARN] 価格系列差の切り分けエラー: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print("  [WARN] eval側の寄与が取得できていないため、比較をスキップします")
                else:
                    print(f"  [WARN] 対象日 {target_date.date()} がweights側の寄与行列に存在しません")
            except Exception as e:
                print(f"  [WARN] 寄与比較エラー: {e}")
                import traceback
                traceback.print_exc()
            
            # 差分原因の分類（寄与ベースで判定）
            print(f"\n[STEP 5] 差分原因の分類（原因ラベル特定）")
            print("=" * 80)
            
            try:
                # 寄与データが利用可能な場合はそれを使用
                if 'merged_contrib' in locals() and len(merged_contrib) > 0:
                    root_cause_label = identify_root_cause_from_contributions(
                        merged_contrib=merged_contrib,
                        port_ret_eval=port_ret_eval,
                        port_ret_weights=port_ret_weights
                    )
                else:
                    # フォールバック: 既存の方法
                    root_cause_label = identify_root_cause(
                        target_date=target_date,
                        port_ret_eval=port_ret_eval,
                        port_ret_weights=port_ret_weights,
                        strategy=strategy,
                        window=window
                    )
                
                print(f"  原因ラベル: {root_cause_label}")
                
            except Exception as e:
                print(f"  [WARN] 原因ラベル特定エラー: {e}")
                import traceback
                traceback.print_exc()
                
                # フォールバック：簡易分類
                if pd.isna(port_ret_eval) or pd.isna(port_ret_weights):
                    print("  分類: 欠損値（一方または両方が欠損）")
                elif abs(diff) < 1e-8:
                    print("  分類: 一致（浮動小数誤差レベル）")
                else:
                    print("  分類: 不一致")
                    print("  考えられる原因:")
                    print("    1. 日付アライン（w[t]をtに適用している／t+1に適用している等）")
                    print("    2. STOPフラグ不一致（STOP判定系列やrolling窓の基準点が違う）")
                    print("    3. 欠損埋め（evalが0で埋めている等）")
                    print("    4. 価格データの差異（adj_close vs close等）")
    
    finally:
        # ファイル出力を閉じる
        if log_file:
            sys.stdout = original_stdout
            log_file.close()
            if output_file:
                print(f"\n[INFO] ログを保存しました: {output_file}")


def identify_root_cause_from_contributions(
    merged_contrib: pd.DataFrame,
    port_ret_eval: float,
    port_ret_weights: float
) -> str:
    """
    寄与データから差分原因を特定
    
    Parameters
    ----------
    merged_contrib : pd.DataFrame
        eval側とweights側の寄与をマージしたDataFrame
        columns: symbol, w_used_eval, ret_eval, contrib_eval, w_used_weights, ret_weights, contrib_weights, contrib_diff, contrib_diff_abs
    port_ret_eval : float
        eval側のポートフォリオリターン
    port_ret_weights : float
        weights側のポートフォリオリターン
    
    Returns
    -------
    str
        原因ラベル（寄与根拠が見える形）
    """
    if pd.isna(port_ret_eval) or pd.isna(port_ret_weights):
        return "missing_value"
    
    diff_original = abs(port_ret_eval - port_ret_weights)
    if diff_original < 1e-8:
        return "match (diff < 1e-8)"
    
    # Top10の寄与差分から原因を判定
    top10_diff = merged_contrib.nlargest(10, "contrib_diff_abs")
    
    # w_diffとret_diffの統計
    w_diffs = (top10_diff["w_used_eval"] - top10_diff["w_used_weights"]).abs()
    ret_diffs = (top10_diff["ret_eval"] - top10_diff["ret_weights"]).abs()
    
    # 原因カテゴリを判定
    causes = []
    
    # 1: date_alignment - w_usedの差分が大きい
    if w_diffs.mean() > 0.01:  # 1%以上の平均差分
        causes.append("1:date_alignment")
    
    # 4: price_diff - retの差分が大きい（w_usedは一致）
    if ret_diffs.mean() > 0.01 and w_diffs.mean() < 0.001:  # ret差分が大きく、w差分が小さい
        causes.append("4:price_diff")
    
    # 3: na_handling - ret_evalまたはret_weightsが0/NaNのケースが多い
    na_ret_eval = top10_diff["ret_eval"].fillna(0.0).abs() < 1e-6
    na_ret_weights = top10_diff["ret_weights"].fillna(0.0).abs() < 1e-6
    if (na_ret_eval | na_ret_weights).sum() >= 3:  # 3銘柄以上で0/NaN
        causes.append("3:na_handling")
    
    # 2: STOP - w_usedが0に近い（または大幅に縮退）ケース
    w_eval_near_zero = top10_diff["w_used_eval"].abs() < 0.001
    w_weights_near_zero = top10_diff["w_used_weights"].abs() < 0.001
    if (w_eval_near_zero | w_weights_near_zero).sum() >= 3:  # 3銘柄以上で0に近い
        causes.append("2:stop_diff")
    
    cause_label = ",".join(causes) if causes else "unknown_multifactorial"
    
    # 統計情報を付加
    result_str = f"cause:{cause_label}"
    result_str += f" | diff:{diff_original:.8f}"
    result_str += f" | top10_w_diff_mean:{w_diffs.mean():.6f}, top10_ret_diff_mean:{ret_diffs.mean():.6f}"
    
    return result_str


def identify_root_cause(
    target_date: pd.Timestamp,
    port_ret_eval: float,
    port_ret_weights: float,
    strategy: str,
    window: int
) -> str:
    """
    差分原因を特定（複数パターンを試して最も一致するものを探索）
    
    Parameters
    ----------
    target_date : pd.Timestamp
        対象日
    port_ret_eval : float
        eval側のポートフォリオリターン
    port_ret_weights : float
        weights側のポートフォリオリターン
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    
    Returns
    -------
    str
        原因ラベル（weights: lag/nolag, price: adj/close, na: drop/zero, stop_apply: yes/no）
    """
    if pd.isna(port_ret_eval) or pd.isna(port_ret_weights):
        return "missing_value"
    
    diff_original = abs(port_ret_eval - port_ret_weights)
    if diff_original < 1e-8:
        return "match (diff < 1e-8)"
    
    # 複数パターンを試す
    patterns = [
        {"weight_lag": True, "adj_close": True, "na_fill": "zero", "name": "lag+adj+zero"},
        {"weight_lag": False, "adj_close": True, "na_fill": "zero", "name": "nolag+adj+zero"},
        {"weight_lag": True, "adj_close": False, "na_fill": "zero", "name": "lag+close+zero"},
        {"weight_lag": False, "adj_close": False, "na_fill": "zero", "name": "nolag+close+zero"},
        {"weight_lag": True, "adj_close": True, "na_fill": "drop", "name": "lag+adj+drop"},
    ]
    
    best_pattern = None
    best_diff = diff_original
    best_port_ret = None
    
    results = []
    
    for pattern in patterns:
        try:
            eval_contrib = calculate_eval_contributions(
                target_date=target_date,
                use_weight_lag=pattern["weight_lag"],
                use_adj_close=pattern["adj_close"],
                na_fill=pattern["na_fill"]
            )
            
            if len(eval_contrib) > 0:
                port_ret_rebuilt = eval_contrib["contribution"].sum()
                diff = abs(port_ret_rebuilt - port_ret_weights)
                
                results.append({
                    "pattern": pattern["name"],
                    "diff": diff,
                    "port_ret": port_ret_rebuilt
                })
                
                if diff < best_diff:
                    best_diff = diff
                    best_pattern = pattern
                    best_port_ret = port_ret_rebuilt
        except Exception as e:
            continue
    
    # 原因ラベルを構築
    if best_pattern and best_diff < diff_original * 0.9:  # 10%以上の改善があれば採用
        weight_label = "lag" if best_pattern["weight_lag"] else "nolag"
        price_label = "adj" if best_pattern["adj_close"] else "close"
        na_label = best_pattern["na_fill"]
        
        # 原因カテゴリを判定
        causes = []
        if weight_label == "nolag" and best_pattern["weight_lag"] != True:
            causes.append("1:date_alignment")
        if price_label == "close":
            causes.append("4:price_diff")
        if na_label == "drop":
            causes.append("3:na_handling")
        
        cause_label = ",".join(causes) if causes else "unknown"
        
        # STOPフラグチェック（簡易版、詳細は後で実装可能）
        stop_label = "unknown"
        
        result_str = f"weights:{weight_label}, price:{price_label}, na:{na_label}, cause:{cause_label}"
        result_str += f" | diff_original:{diff_original:.8f}, diff_best:{best_diff:.8f}, improvement:{(1-best_diff/diff_original)*100:.1f}%"
        
        return result_str
    else:
        # 改善がなければ原因不明
        return f"unknown_multifactorial | diff:{diff_original:.8f}, no_pattern_improves >10%"


def load_top_diff_dates(strategy: str, window: int, top_n: int = 10) -> list:
    """
    比較結果から差分が大きい日をTop N抽出
    
    Parameters
    ----------
    strategy : str
        戦略名
    window : int
        ウィンドウサイズ
    top_n : int
        抽出する日数（デフォルト: 10）
    
    Returns
    -------
    list
        対象日のリスト（YYYY-MM-DD形式の文字列）
    """
    comparison_path = RESEARCH_REPORTS_DIR / f"eval_vs_weights_comparison_{strategy}_w{window}.parquet"
    
    if not comparison_path.exists():
        print(f"[WARN] 比較結果ファイルが見つかりません: {comparison_path}")
        return []
    
    try:
        df = pd.read_parquet(comparison_path)
        
        if "abs_diff" not in df.columns:
            print(f"[WARN] abs_diff列が見つかりません")
            return []
        
        # 差分が大きい順にソート
        df_sorted = df.nlargest(top_n, "abs_diff")
        
        # 日付を文字列に変換
        dates = df_sorted["trade_date"].dt.strftime("%Y-%m-%d").tolist()
        
        return dates
    except Exception as e:
        print(f"[WARN] 比較結果の読み込みエラー: {e}")
        return []


def run_all_analysis(output_file: str = None):
    """
    全戦略・全ウィンドウについて、差分が大きい日を自動抽出して分析
    
    Parameters
    ----------
    output_file : str, optional
        出力ファイルパス（指定しない場合は出力しない）
    """
    strategies = ["stop0", "planA", "planB"]
    windows = [60, 120]
    top_n = 10  # 各戦略・ウィンドウについてTop 10日を分析
    
    # ファイル出力を設定
    original_stdout = sys.stdout
    log_file = None
    
    if output_file:
        log_file_path = Path(output_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_file_path, 'w', encoding='utf-8')
        sys.stdout = TeeOutput(original_stdout, log_file)
    
    try:
        print("=" * 80)
        print("=== eval_stop_regimes vs backtest_from_weights_with_stop 差分詳細分析（全量実行） ===")
        print("=" * 80)
        
        all_dates_to_analyze = {}
        
        # まず、各戦略・ウィンドウの差分が大きい日を抽出
        print("\n[STEP 0] 差分が大きい日を抽出中...")
        for strategy in strategies:
            for window in windows:
                key = f"{strategy}_w{window}"
                dates = load_top_diff_dates(strategy, window, top_n=top_n)
                if dates:
                    all_dates_to_analyze[key] = dates
                    print(f"  {strategy.upper()} w{window}: {len(dates)} 日抽出")
                else:
                    print(f"  {strategy.upper()} w{window}: 抽出できませんでした")
        
        # 各戦略・ウィンドウについて分析実行
        for strategy in strategies:
            for window in windows:
                key = f"{strategy}_w{window}"
                dates = all_dates_to_analyze.get(key, [])
                
                if not dates:
                    print(f"\n[SKIP] {strategy.upper()} w{window}: 分析対象日がありません")
                    continue
                
                print(f"\n{'='*80}")
                print(f"=== {strategy.upper()} (window={window}) の分析 ===")
                print(f"{'='*80}")
                
                # Top 3日のみ詳細分析（出力が多くなりすぎないように）
                for i, date_str in enumerate(dates[:3], 1):
                    print(f"\n[分析 {i}/{min(3, len(dates))}] {date_str}")
                    print("-" * 80)
                    try:
                        analyze_date_difference(
                            strategy=strategy,
                            window=window,
                            target_date_str=date_str,
                            n_prev=3,
                            n_next=3,
                            output_file=None  # 全量実行の場合は個別ファイル出力はしない
                        )
                    except Exception as e:
                        print(f"[ERROR] {date_str} の分析でエラー: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
    
    finally:
        # ファイル出力を閉じる
        if log_file:
            sys.stdout = original_stdout
            log_file.close()
            if output_file:
                print(f"\n[INFO] ログを保存しました: {output_file}")


def main():
    """メイン関数"""
    import argparse
    
    RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
    
    parser = argparse.ArgumentParser(
        description="eval_stop_regimes.py と backtest_from_weights_with_stop.py の差分を特定日について詳細分析"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=False,
        choices=["stop0", "planA", "planB", "all"],
        default="all",
        help="戦略（stop0, planA, planB, all）。デフォルト: all（全戦略を実行）"
    )
    parser.add_argument(
        "--window",
        type=int,
        required=False,
        choices=[60, 120],
        default=None,
        help="ウィンドウサイズ（60, 120）。--strategy=allの場合は無視される"
    )
    parser.add_argument(
        "--date",
        type=str,
        required=False,
        default=None,
        help="対象日（YYYY-MM-DD）。--strategy=allの場合は無視される"
    )
    parser.add_argument(
        "--n_prev",
        type=int,
        default=3,
        help="対象日の前日数（デフォルト: 3）"
    )
    parser.add_argument(
        "--n_next",
        type=int,
        default=3,
        help="対象日の後日数（デフォルト: 3）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力ファイルパス（指定しない場合は自動生成）"
    )
    
    args = parser.parse_args()
    
    # 出力ファイルパスの自動生成（指定がない場合）
    output_file = args.output
    if output_file is None:
        if args.strategy == "all":
            # 全量実行の場合はタイムスタンプ付きファイル名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(RESEARCH_REPORTS_DIR / f"debug_eval_vs_weights_all_{timestamp}.txt")
        else:
            # 単一日分析の場合は戦略・ウィンドウ・日付を含むファイル名
            date_str_clean = args.date.replace("-", "")
            output_file = str(RESEARCH_REPORTS_DIR / f"debug_eval_vs_weights_{args.strategy}_w{args.window}_{date_str_clean}.txt")
    
    # 全量実行モード
    if args.strategy == "all":
        run_all_analysis(output_file=output_file)
    else:
        # 単一日分析モード（従来通り）
        if args.date is None:
            parser.error(f"--date は {args.strategy} の場合必須です")
        if args.window is None:
            parser.error(f"--window は {args.strategy} の場合必須です")
        
        analyze_date_difference(
            strategy=args.strategy,
            window=args.window,
            target_date_str=args.date,
            n_prev=args.n_prev,
            n_next=args.n_next,
            output_file=output_file
        )


if __name__ == "__main__":
    main()

