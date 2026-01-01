#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/ops/compare_core_vs_backtest.py

core vs backtest 完全一致検証スクリプト

目的（合格条件）:
同一入力（weights・prices・calendar）で、
- daily portfolio return
- alpha return（TOPIX差引）
- STOPフラグ/レジーム（将来拡張）
- 日次PnL（任意）
が一致すること。

実装方針:
1) "正本"を決めて固定
   - calendar正本：index_tpx_daily.parquet の date（TPX営業日）
   - return定義：adj_close.pct_change()（core/backtest共通）
   - 適用ルール：ret[t] = Σ w[t-1] * r[t]（絶対）
   - 欠損日：drop（bfill禁止）

2) 比較する系列を2本作る
   - Series A（core再構築）：daily_portfolio_guarded.parquet を "重みの正本"として、pricesから w[t-1]*r[t] を再構築
   - Series B（backtest出力）：backtest_from_weights.py の計算ロジックを使用

3) まずSTOPなしで一致させる（難易度を落とす）

入力:
- data/processed/daily_portfolio_guarded.parquet
- data/raw/prices/prices_*.csv（or parquet）
- data/processed/index_tpx_daily.parquet

出力:
- data/processed/diagnostics/core_vs_bt_diff_daily.csv
- data/processed/diagnostics/mismatch_first_day.json（最初の不一致日について）
"""

import sys
import io
import os
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

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

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from scripts.tools.lib import data_loader

DATA_DIR = Path("data/processed")
DIAGNOSTICS_DIR = DATA_DIR / "diagnostics"
DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)

# 許容誤差（超厳格）
TOLERANCE = 1e-12


def load_calendar() -> pd.Series:
    """
    calendar正本を読み込む（index_tpx_daily.parquet の date）
    
    Returns
    -------
    pd.Series
        TPX営業日の日付系列（昇順、timezoneなし）
    """
    tpx_path = DATA_DIR / "index_tpx_daily.parquet"
    if not tpx_path.exists():
        raise FileNotFoundError(f"calendar正本が見つかりません: {tpx_path}")
    
    df_tpx = pd.read_parquet(tpx_path)
    
    # dateカラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df_tpx.columns:
            date_col = col
            break
    
    if date_col is None:
        raise ValueError(f"dateカラムが見つかりません。カラム: {df_tpx.columns.tolist()}")
    
    dates = pd.to_datetime(df_tpx[date_col]).dt.normalize()
    dates = dates.drop_duplicates().sort_values().reset_index(drop=True)
    
    print(f"[INFO] calendar正本: {len(dates)} 日 ({dates.min()} ～ {dates.max()})")
    
    return dates


def calculate_returns_core_series(
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame,
    calendar: pd.Series
) -> pd.DataFrame:
    """
    core系列を再構築: daily_portfolio_guarded.parquet から w[t-1]*r[t] を計算
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame（daily_portfolio_guarded.parquet）
    prices_df : pd.DataFrame
        価格データ（symbol, date, adj_close を含む）
    calendar : pd.Series
        TPX営業日カレンダー（正本）
    
    Returns
    -------
    pd.DataFrame
        date, ret_core, contrib_by_symbol（シンボルごとの寄与）を含むDataFrame
    """
    # リターンを計算（adj_close.pct_change()）
    prices_df = prices_df.sort_values(["symbol", "date"])
    if "adj_close" in prices_df.columns:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["adj_close"].pct_change()
    else:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
    
    # weightsを日付でソート（asof merge用）
    df_weights = df_weights.sort_values(["date", "symbol"])
    df_weights["date"] = pd.to_datetime(df_weights["date"]).dt.normalize()
    df_weights_indexed = df_weights.set_index("date")
    
    rows = []
    
    # calendarの日付でループ（最初の日は前日がないのでスキップ）
    for i in range(1, len(calendar)):
        trade_date = calendar.iloc[i]
        prev_date = calendar.iloc[i - 1]
        
        # 前日のweightsを取得（w[t-1]）
        weights_prev = df_weights_indexed[df_weights_indexed.index <= prev_date]
        if weights_prev.empty:
            continue
        
        # 前日の日付で最新のweightsを取得
        weights_day = weights_prev[weights_prev.index == weights_prev.index.max()].copy()
        if weights_day.empty:
            continue
        
        # 前日のweightsをSeriesに変換（symbolをindexに）
        weights_series = weights_day.reset_index().set_index("symbol")["weight"]
        
        # 当日の価格データを取得（r[t]）
        prices_day = prices_df[prices_df["date"] == trade_date].copy()
        if prices_day.empty:
            continue
        
        prices_day = prices_day.set_index("symbol")
        
        # 共通のsymbolを取得
        common_symbols = weights_series.index.intersection(prices_day.index)
        if len(common_symbols) == 0:
            continue
        
        # 共通symbolのweightsとreturnsを取得
        weights_aligned = weights_series[common_symbols].fillna(0.0)
        rets_aligned = prices_day.loc[common_symbols, "ret_1d"].fillna(0.0)
        
        # ポートフォリオリターンを計算: port_ret[t] = sum_i w_i[t-1] * r_i[t]
        contrib = weights_aligned * rets_aligned
        port_ret_cc = float(contrib.sum())
        
        # シンボルごとの寄与を記録（デバッグ用）
        contrib_dict = contrib.to_dict()
        contrib_dict = {str(k): float(v) for k, v in contrib_dict.items() if abs(v) > 1e-10}
        
        # w[t]r[t]も同時に計算（backtestが誤って同日weightsを使っていないかチェック用）
        # 当日のweightsを取得（w[t]）
        weights_today = df_weights_indexed[df_weights_indexed.index <= trade_date]
        match_same_ratio = None
        if not weights_today.empty:
            weights_today_day = weights_today[weights_today.index == weights_today.index.max()].copy()
            if not weights_today_day.empty:
                weights_today_series = weights_today_day.reset_index().set_index("symbol")["weight"]
                # common_symbolsとweights_today_series.indexの共通部分を使用
                common_today = common_symbols.intersection(weights_today_series.index)
                if len(common_today) > 0:
                    weights_today_aligned = weights_today_series[common_today].fillna(0.0)
                    rets_today_aligned = rets_aligned[common_today].fillna(0.0)
                    contrib_same_day = weights_today_aligned * rets_today_aligned
                    port_ret_same_day = float(contrib_same_day.sum())
                    
                    # 同じ日のweightsを使った場合のリターンとの比率
                    if abs(port_ret_cc) > 1e-10:
                        match_same_ratio = port_ret_same_day / port_ret_cc
                    elif abs(port_ret_same_day) > 1e-10:
                        match_same_ratio = float('inf')
                    else:
                        match_same_ratio = 1.0
        
        rows.append({
            "date": trade_date,
            "ret_core": port_ret_cc,
            "contrib_by_symbol": contrib_dict,
            "w_prev_date": prev_date,
            "match_same_ratio": match_same_ratio,  # w[t]r[t] / w[t-1]r[t] の比率
        })
    
    df_result = pd.DataFrame(rows)
    
    if df_result.empty:
        return pd.DataFrame(columns=["date", "ret_core", "contrib_by_symbol", "w_prev_date"])
    
    return df_result.sort_values("date").reset_index(drop=True)


def calculate_returns_backtest_series(
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame,
    calendar: pd.Series
) -> pd.DataFrame:
    """
    backtest系列を計算: backtest_from_weights.py と同じロジック
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame
    prices_df : pd.DataFrame
        価格データ
    calendar : pd.Series
        TPX営業日カレンダー（正本）
    
    Returns
    -------
    pd.DataFrame
        date, ret_bt, contrib_by_symbol を含むDataFrame
    """
    # リターンを計算（adj_close.pct_change()）
    prices_df = prices_df.sort_values(["symbol", "date"])
    if "adj_close" in prices_df.columns:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["adj_close"].pct_change()
    else:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
    
    # trade_datesはcalendarを使用（backtest_from_weights.pyの実装に合わせる）
    trade_dates = calendar.tolist()
    
    # weightsを日付でソート（asof merge用）
    df_weights = df_weights.sort_values(["date", "symbol"])
    df_weights["date"] = pd.to_datetime(df_weights["date"]).dt.normalize()
    df_weights_indexed = df_weights.set_index("date")
    
    rows = []
    
    for i, trade_date in enumerate(trade_dates):
        # 最初の日は前日がないのでスキップ
        if i == 0:
            continue
        
        # 前日のweightsを取得（w[t-1]）
        prev_date = trade_dates[i - 1]
        
        # asof merge: 前日以前の最新のweightsを使用
        weights_prev = df_weights_indexed[df_weights_indexed.index <= prev_date]
        if weights_prev.empty:
            continue
        
        # 前日の日付で最新のweightsを取得
        weights_day = weights_prev[weights_prev.index == weights_prev.index.max()].copy()
        if weights_day.empty:
            continue
        
        # 前日のweightsをSeriesに変換（symbolをindexに）
        weights_series = weights_day.reset_index().set_index("symbol")["weight"]
        
        # 当日の価格データを取得（r[t]）
        prices_day = prices_df[prices_df["date"] == trade_date].copy()
        if prices_day.empty:
            continue
        
        prices_day = prices_day.set_index("symbol")
        
        # 共通のsymbolを取得
        common_symbols = weights_series.index.intersection(prices_day.index)
        if len(common_symbols) == 0:
            continue
        
        # 共通symbolのweightsとreturnsを取得
        weights_aligned = weights_series[common_symbols].fillna(0.0)
        rets_aligned = prices_day.loc[common_symbols, "ret_1d"].fillna(0.0)
        
        # ポートフォリオリターンを計算: port_ret[t] = sum_i w_i[t-1] * r_i[t]
        contrib = weights_aligned * rets_aligned
        port_ret_cc = float(contrib.sum())
        
        # シンボルごとの寄与を記録（デバッグ用）
        contrib_dict = contrib.to_dict()
        contrib_dict = {str(k): float(v) for k, v in contrib_dict.items() if abs(v) > 1e-10}
        
        # w[t]r[t]も同時に計算（backtestが誤って同日weightsを使っていないかチェック用）
        # 当日のweightsを取得（w[t]）
        weights_today = df_weights_indexed[df_weights_indexed.index <= trade_date]
        match_same_ratio = None
        if not weights_today.empty:
            weights_today_day = weights_today[weights_today.index == weights_today.index.max()].copy()
            if not weights_today_day.empty:
                weights_today_series = weights_today_day.reset_index().set_index("symbol")["weight"]
                # common_symbolsとweights_today_series.indexの共通部分を使用
                common_today = common_symbols.intersection(weights_today_series.index)
                if len(common_today) > 0:
                    weights_today_aligned = weights_today_series[common_today].fillna(0.0)
                    rets_today_aligned = rets_aligned[common_today].fillna(0.0)
                    contrib_same_day = weights_today_aligned * rets_today_aligned
                    port_ret_same_day = float(contrib_same_day.sum())
                    
                    # 同じ日のweightsを使った場合のリターンとの比率
                    if abs(port_ret_cc) > 1e-10:
                        match_same_ratio = port_ret_same_day / port_ret_cc
                    elif abs(port_ret_same_day) > 1e-10:
                        match_same_ratio = float('inf')
                    else:
                        match_same_ratio = 1.0
        
        rows.append({
            "date": trade_date,
            "ret_bt": port_ret_cc,
            "contrib_by_symbol": contrib_dict,
            "w_prev_date": prev_date,
            "match_same_ratio": match_same_ratio,  # w[t]r[t] / w[t-1]r[t] の比率
        })
    
    df_result = pd.DataFrame(rows)
    
    if df_result.empty:
        return pd.DataFrame(columns=["date", "ret_bt", "contrib_by_symbol", "w_prev_date"])
    
    return df_result.sort_values("date").reset_index(drop=True)


def get_day_details(
    mismatch_date: pd.Timestamp,
    w_prev_date: pd.Timestamp,
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame
) -> Dict:
    """
    不一致日の詳細を取得（w[t-1], r[t], contrib等）
    
    Parameters
    ----------
    mismatch_date : pd.Timestamp
        不一致日（t）
    w_prev_date : pd.Timestamp
        前日の日付（t-1）
    df_weights : pd.DataFrame
        weightsデータ
    prices_df : pd.DataFrame
        価格データ
    
    Returns
    -------
    Dict
        その日の詳細情報
    """
    # w[t-1]を取得
    df_weights = df_weights.sort_values(["date", "symbol"])
    df_weights["date"] = pd.to_datetime(df_weights["date"]).dt.normalize()
    df_weights_indexed = df_weights.set_index("date")
    
    weights_prev = df_weights_indexed[df_weights_indexed.index <= w_prev_date]
    if not weights_prev.empty:
        weights_day = weights_prev[weights_prev.index == weights_prev.index.max()].copy()
        if not weights_day.empty:
            w_prev = weights_day.reset_index()[["symbol", "weight"]].to_dict("records")
            w_prev_dict = {str(row["symbol"]): float(row["weight"]) for row in w_prev}
        else:
            w_prev_dict = {}
    else:
        w_prev_dict = {}
    
    # r[t]を取得
    prices_df = prices_df.sort_values(["symbol", "date"])
    if "adj_close" in prices_df.columns:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["adj_close"].pct_change()
    else:
        prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
    
    prices_day = prices_df[prices_df["date"] == mismatch_date].copy()
    if not prices_day.empty:
        r_t = prices_day[["symbol", "ret_1d", "adj_close", "close"]].to_dict("records")
        r_t_dict = {}
        for row in r_t:
            symbol = str(row["symbol"])
            r_t_dict[symbol] = {
                "ret_1d": float(row["ret_1d"]) if pd.notna(row["ret_1d"]) else None,
                "adj_close": float(row["adj_close"]) if pd.notna(row["adj_close"]) else None,
                "close": float(row["close"]) if pd.notna(row["close"]) else None,
            }
    else:
        r_t_dict = {}
    
    # contrib = w[t-1] * r[t] を計算
    contrib_dict = {}
    for symbol in set(w_prev_dict.keys()) & set(r_t_dict.keys()):
        w = w_prev_dict.get(symbol, 0.0)
        r = r_t_dict[symbol].get("ret_1d", 0.0) if r_t_dict[symbol].get("ret_1d") is not None else 0.0
        contrib = w * r
        if abs(contrib) > 1e-10:
            contrib_dict[symbol] = {
                "w_prev": w,
                "r_t": r,
                "contrib": contrib
            }
    
    return {
        "w_prev": w_prev_dict,
        "r_t": r_t_dict,
        "contrib": contrib_dict
    }


def calculate_alpha_series(
    df_returns: pd.DataFrame,
    df_weights: pd.DataFrame,
    df_tpx: pd.DataFrame,
    calendar: pd.Series,
    beta_type: str = "equity_cash"
) -> pd.DataFrame:
    """
    alpha系列を計算: alpha[t] = ret_port[t] - beta[t-1] * ret_tpx[t]
    
    Parameters
    ----------
    df_returns : pd.DataFrame
        ポートフォリオリターン（date, ret_port）
    df_weights : pd.DataFrame
        weightsデータ（date, symbol, weight, beta_equity_cash等）
    df_tpx : pd.DataFrame
        TOPIXデータ（trade_date, tpx_ret_cc）
    calendar : pd.Series
        TPX営業日カレンダー
    beta_type : str
        "equity_cash" または "equity_cfd"
    
    Returns
    -------
    pd.DataFrame
        date, alpha, beta_prev, ret_tpx を含むDataFrame
    """
    # betaカラム名
    beta_col = f"beta_{beta_type}"
    if beta_col not in df_weights.columns:
        raise ValueError(f"betaカラムが見つかりません: {beta_col}")
    
    # weightsを日付でソート
    df_weights = df_weights.sort_values("date")
    df_weights["date"] = pd.to_datetime(df_weights["date"]).dt.normalize()
    
    # 日付ごとにbeta[t-1]を取得（asof merge）
    df_weights_indexed = df_weights.set_index("date")
    
    # TPXデータを準備
    df_tpx = df_tpx.copy()
    date_col = "trade_date" if "trade_date" in df_tpx.columns else "date"
    df_tpx[date_col] = pd.to_datetime(df_tpx[date_col]).dt.normalize()
    df_tpx = df_tpx.set_index(date_col)
    
    # ret_portカラムを確認
    if "ret_port" not in df_returns.columns:
        # ret_coreまたはret_btがある場合はret_portにリネーム
        if "ret_core" in df_returns.columns:
            df_returns = df_returns.rename(columns={"ret_core": "ret_port"})
        elif "ret_bt" in df_returns.columns:
            df_returns = df_returns.rename(columns={"ret_bt": "ret_port"})
        else:
            raise ValueError(f"ret_port, ret_core, ret_btのいずれかのカラムが必要です。カラム: {df_returns.columns.tolist()}")
    
    rows = []
    
    for i in range(1, len(calendar)):
        trade_date = calendar.iloc[i]
        prev_date = calendar.iloc[i - 1]
        
        # 当日のポートフォリオリターンを取得
        ret_row = df_returns[df_returns["date"] == trade_date]
        if ret_row.empty:
            continue
        ret_port = ret_row["ret_port"].iloc[0]
        if pd.isna(ret_port):
            continue
        
        # 前日のbetaを取得（w[t-1]と同様にasof merge）
        weights_prev = df_weights_indexed[df_weights_indexed.index <= prev_date]
        if weights_prev.empty:
            continue
        
        weights_day = weights_prev[weights_prev.index == weights_prev.index.max()]
        if weights_day.empty:
            continue
        
        # beta[t-1]を取得（最初の行のbeta値を使用、全行同じ値のはず）
        beta_prev = weights_day[beta_col].iloc[0] if beta_col in weights_day.columns else None
        if pd.isna(beta_prev) or beta_prev is None:
            continue
        
        # 当日のTOPIXリターンを取得
        if trade_date in df_tpx.index:
            ret_tpx = df_tpx.loc[trade_date, "tpx_ret_cc"]
            if pd.isna(ret_tpx):
                continue
        else:
            continue
        
        # alpha計算: alpha[t] = ret_port[t] - beta[t-1] * ret_tpx[t]
        alpha = ret_port - beta_prev * ret_tpx
        
        rows.append({
            "date": trade_date,
            "alpha": alpha,
            "ret_port": ret_port,
            "beta_prev": beta_prev,
            "ret_tpx": ret_tpx,
            "w_prev_date": prev_date,
        })
    
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def compare_series(
    df_core: pd.DataFrame,
    df_bt: pd.DataFrame,
    calendar: pd.Series,
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame,
    compare_alpha: bool = False,
    df_tpx: Optional[pd.DataFrame] = None
) -> Tuple[pd.DataFrame, Optional[Dict]]:
    """
    core系列とbacktest系列を比較
    
    Parameters
    ----------
    df_core : pd.DataFrame
        core系列（date, ret_core）
    df_bt : pd.DataFrame
        backtest系列（date, ret_bt）
    calendar : pd.Series
        TPX営業日カレンダー
    df_weights : pd.DataFrame
        weightsデータ（詳細ダンプ用）
    prices_df : pd.DataFrame
        価格データ（詳細ダンプ用）
    
    Returns
    -------
    pd.DataFrame
        比較結果（date, ret_core, ret_bt, diff, ...）
    Optional[Dict]
        最初の不一致日の詳細（一致する場合はNone）
    """
    # calendarに基づいてmerge
    df_cal = pd.DataFrame({"date": calendar})
    
    # core系列をmerge
    df_compare = df_cal.merge(
        df_core[["date", "ret_core", "contrib_by_symbol", "w_prev_date", "match_same_ratio"]],
        on="date",
        how="left"
    )
    
    # backtest系列をmerge
    df_compare = df_compare.merge(
        df_bt[["date", "ret_bt", "contrib_by_symbol", "w_prev_date", "match_same_ratio"]],
        on="date",
        suffixes=("_core", "_bt"),
        how="left"
    )
    
    # 差分を計算
    df_compare["diff"] = df_compare["ret_core"] - df_compare["ret_bt"]
    df_compare["abs_diff"] = df_compare["diff"].abs()
    
    # 最大寄与シンボルを抽出（core側）
    def get_max_contrib_symbol(contrib_dict):
        if pd.isna(contrib_dict) or not contrib_dict:
            return None
        if isinstance(contrib_dict, dict):
            if not contrib_dict:
                return None
            max_symbol = max(contrib_dict.items(), key=lambda x: abs(x[1]))
            return max_symbol[0] if max_symbol else None
        return None
    
    df_compare["max_abs_contrib_symbol"] = df_compare["contrib_by_symbol_core"].apply(get_max_contrib_symbol)
    
    # 最初の不一致日を特定
    mismatch_first_day = None
    mismatch_idx = None
    
    for idx, row in df_compare.iterrows():
        if pd.isna(row["ret_core"]) or pd.isna(row["ret_bt"]):
            continue
        
        if abs(row["diff"]) > TOLERANCE:
            mismatch_first_day = row["date"]
            mismatch_idx = idx
            break
    
    # 最初の不一致日の詳細を抽出
    mismatch_detail = None
    if mismatch_first_day is not None:
        mismatch_row = df_compare.iloc[mismatch_idx]
        
        # w[t-1]とr[t]を取得
        w_prev_date = mismatch_row["w_prev_date_core"]
        if pd.isna(w_prev_date):
            w_prev_date = mismatch_row["w_prev_date_bt"]
        
        # その日の詳細を取得
        day_details = get_day_details(
            mismatch_row["date"],
            w_prev_date,
            df_weights,
            prices_df
        )
        
        mismatch_detail = {
            "mismatch_date": str(mismatch_row["date"]),
            "w_prev_date": str(w_prev_date),
            "ret_core": float(mismatch_row["ret_core"]) if pd.notna(mismatch_row["ret_core"]) else None,
            "ret_bt": float(mismatch_row["ret_bt"]) if pd.notna(mismatch_row["ret_bt"]) else None,
            "diff": float(mismatch_row["diff"]),
            "abs_diff": float(mismatch_row["abs_diff"]),
            "contrib_by_symbol_core": mismatch_row["contrib_by_symbol_core"] if pd.notna(mismatch_row["contrib_by_symbol_core"]) else {},
            "contrib_by_symbol_bt": mismatch_row["contrib_by_symbol_bt"] if pd.notna(mismatch_row["contrib_by_symbol_bt"]) else {},
            "match_same_ratio_core": float(mismatch_row["match_same_ratio_core"]) if pd.notna(mismatch_row["match_same_ratio_core"]) else None,
            "match_same_ratio_bt": float(mismatch_row["match_same_ratio_bt"]) if pd.notna(mismatch_row["match_same_ratio_bt"]) else None,
            "w_prev": day_details["w_prev"],
            "r_t": day_details["r_t"],
            "contrib_w_prev_r_t": day_details["contrib"],
        }
    
    return df_compare, mismatch_detail


def main():
    """メイン関数"""
    import argparse
    
    global TOLERANCE
    
    parser = argparse.ArgumentParser(
        description="core vs backtest 完全一致検証"
    )
    parser.add_argument(
        "--portfolio",
        type=str,
        default=str(DATA_DIR / "daily_portfolio_guarded.parquet"),
        help="core portfolioファイルのパス"
    )
    parser.add_argument(
        "--output-diff",
        type=str,
        default=str(DIAGNOSTICS_DIR / "core_vs_bt_diff_daily.csv"),
        help="差分CSV出力パス"
    )
    parser.add_argument(
        "--output-mismatch",
        type=str,
        default=str(DIAGNOSTICS_DIR / "mismatch_first_day.json"),
        help="最初の不一致日JSON出力パス"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=TOLERANCE,
        help=f"許容誤差（デフォルト: {TOLERANCE}）"
    )
    parser.add_argument(
        "--alpha",
        action="store_true",
        help="alpha系列も比較する（alpha[t] = ret_port[t] - beta[t-1] * ret_tpx[t]）"
    )
    parser.add_argument(
        "--beta-type",
        type=str,
        default="equity_cash",
        choices=["equity_cash", "equity_cfd"],
        help="使用するbetaタイプ（デフォルト: equity_cash）"
    )
    
    args = parser.parse_args()
    TOLERANCE = args.tolerance
    
    print("=" * 80)
    print("=== core vs backtest 完全一致検証 ===")
    print("=" * 80)
    
    # 1. calendar正本を読み込む
    print("\n[STEP 1] calendar正本を読み込み中...")
    try:
        calendar = load_calendar()
        print(f"  ✓ {len(calendar)} 日")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # 2. core portfolioを読み込む
    print("\n[STEP 2] core portfolioを読み込み中...")
    portfolio_path = Path(args.portfolio)
    if not portfolio_path.exists():
        print(f"  ✗ ファイルが見つかりません: {portfolio_path}")
        return 1
    
    try:
        df_portfolio = pd.read_parquet(portfolio_path)
        df_portfolio["date"] = pd.to_datetime(df_portfolio["date"]).dt.normalize()
        print(f"  ✓ {len(df_portfolio)} 行")
        print(f"  日付範囲: {df_portfolio['date'].min()} ～ {df_portfolio['date'].max()}")
        
        # 必須カラムを確認
        required_cols = ["date", "symbol", "weight"]
        missing_cols = [col for col in required_cols if col not in df_portfolio.columns]
        if missing_cols:
            print(f"  ✗ 必須カラムが不足しています: {missing_cols}")
            return 1
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 3. 価格データを読み込む
    print("\n[STEP 3] 価格データを読み込み中...")
    try:
        prices_df = data_loader.load_prices()
        prices_df["date"] = pd.to_datetime(prices_df["date"]).dt.normalize()
        print(f"  ✓ {len(prices_df)} 行")
        print(f"  銘柄数: {prices_df['symbol'].nunique()}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 4. core系列を再構築
    print("\n[STEP 4] core系列を再構築中...")
    try:
        df_core = calculate_returns_core_series(df_portfolio, prices_df, calendar)
        print(f"  ✓ {len(df_core)} 日分のリターンを計算")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 5. backtest系列を計算
    print("\n[STEP 5] backtest系列を計算中...")
    try:
        df_bt = calculate_returns_backtest_series(df_portfolio, prices_df, calendar)
        print(f"  ✓ {len(df_bt)} 日分のリターンを計算")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 6. TOPIXデータを読み込む（alpha比較用）
    df_tpx = None
    if args.alpha:
        print("\n[STEP 6] TOPIXデータを読み込み中（alpha比較用）...")
        try:
            tpx_path = DATA_DIR / "index_tpx_daily.parquet"
            if not tpx_path.exists():
                print(f"  ✗ ファイルが見つかりません: {tpx_path}")
                print(f"  → alpha比較をスキップします")
                args.alpha = False
            else:
                df_tpx = pd.read_parquet(tpx_path)
                print(f"  ✓ {len(df_tpx)} 行")
        except Exception as e:
            print(f"  ✗ エラー: {e}")
            print(f"  → alpha比較をスキップします")
            args.alpha = False
    
    # 7. 比較
    step_num = 7 if args.alpha else 6
    print(f"\n[STEP {step_num}] 比較中...")
    try:
        df_compare, mismatch_detail = compare_series(
            df_core, df_bt, calendar, df_portfolio, prices_df,
            compare_alpha=args.alpha,
            df_tpx=df_tpx
        )
        print(f"  ✓ 比較完了")
        
        # 統計情報
        valid_rows = df_compare.dropna(subset=["ret_core", "ret_bt"])
        if len(valid_rows) > 0:
            max_abs_diff = valid_rows["abs_diff"].max()
            mean_abs_diff = valid_rows["abs_diff"].mean()
            print(f"\n  比較日数: {len(valid_rows)} 日")
            print(f"  最大絶対差分: {max_abs_diff:.2e}")
            print(f"  平均絶対差分: {mean_abs_diff:.2e}")
            print(f"  許容誤差: {TOLERANCE:.2e}")
            
            if max_abs_diff <= TOLERANCE:
                print(f"\n  ✓✓✓ 合格: 完全一致（max_abs_diff <= {TOLERANCE:.2e}）")
            else:
                print(f"\n  ✗✗✗ 不合格: 不一致検出（max_abs_diff = {max_abs_diff:.2e} > {TOLERANCE:.2e}）")
        else:
            print(f"  ⚠ 比較可能な日がありません")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 8. alpha系列の比較（オプション）
    if args.alpha and df_tpx is not None:
        step_num = 8
        print(f"\n[STEP {step_num}] alpha系列を計算・比較中...")
        try:
            # core系列のalphaを計算
            df_alpha_core = calculate_alpha_series(
                df_core.rename(columns={"ret_core": "ret_port"}),
                df_portfolio,
                df_tpx,
                calendar,
                beta_type=args.beta_type
            )
            df_alpha_core = df_alpha_core.rename(columns={"alpha": "alpha_core", "ret_port": "ret_port_core", "beta_prev": "beta_prev_core", "ret_tpx": "ret_tpx_core"})
            
            # backtest系列のalphaを計算
            df_alpha_bt = calculate_alpha_series(
                df_bt.rename(columns={"ret_bt": "ret_port"}),
                df_portfolio,
                df_tpx,
                calendar,
                beta_type=args.beta_type
            )
            df_alpha_bt = df_alpha_bt.rename(columns={"alpha": "alpha_bt", "ret_port": "ret_port_bt", "beta_prev": "beta_prev_bt", "ret_tpx": "ret_tpx_bt"})
            
            # alpha系列をmerge
            df_alpha_compare = pd.DataFrame({"date": calendar})
            df_alpha_compare = df_alpha_compare.merge(df_alpha_core, on="date", how="left")
            df_alpha_compare = df_alpha_compare.merge(df_alpha_bt, on="date", how="left")
            
            # 差分を計算
            df_alpha_compare["alpha_diff"] = df_alpha_compare["alpha_core"] - df_alpha_compare["alpha_bt"]
            df_alpha_compare["alpha_abs_diff"] = df_alpha_compare["alpha_diff"].abs()
            
            # 統計情報
            valid_alpha = df_alpha_compare.dropna(subset=["alpha_core", "alpha_bt"])
            if len(valid_alpha) > 0:
                max_abs_alpha_diff = valid_alpha["alpha_abs_diff"].max()
                mean_abs_alpha_diff = valid_alpha["alpha_abs_diff"].mean()
                print(f"\n  alpha比較日数: {len(valid_alpha)} 日")
                print(f"  最大絶対差分: {max_abs_alpha_diff:.2e}")
                print(f"  平均絶対差分: {mean_abs_alpha_diff:.2e}")
                
                if max_abs_alpha_diff <= TOLERANCE:
                    print(f"\n  ✓✓✓ alpha合格: 完全一致（max_abs_diff <= {TOLERANCE:.2e}）")
                else:
                    print(f"\n  ✗✗✗ alpha不合格: 不一致検出（max_abs_diff = {max_abs_alpha_diff:.2e} > {TOLERANCE:.2e}）")
                    
                    # 最初の不一致日を特定
                    for idx, row in valid_alpha.iterrows():
                        if abs(row["alpha_diff"]) > TOLERANCE:
                            print(f"\n  最初のalpha不一致日: {row['date']}")
                            print(f"    alpha_core: {row['alpha_core']:.6e}")
                            print(f"    alpha_bt: {row['alpha_bt']:.6e}")
                            print(f"    diff: {row['alpha_diff']:.6e}")
                            print(f"    beta_prev_core: {row.get('beta_prev_core', 'N/A')}")
                            print(f"    beta_prev_bt: {row.get('beta_prev_bt', 'N/A')}")
                            print(f"    ret_tpx: {row.get('ret_tpx_core', row.get('ret_tpx_bt', 'N/A'))}")
                            break
            else:
                print(f"  ⚠ alpha比較可能な日がありません")
            
            # alpha比較結果を保存
            alpha_output_path = Path(args.output_diff).parent / "core_vs_bt_alpha_diff_daily.csv"
            df_alpha_compare.to_csv(alpha_output_path, index=False)
            print(f"  ✓ alpha差分CSV: {alpha_output_path}")
            
        except Exception as e:
            print(f"  ✗ alpha比較エラー: {e}")
            import traceback
            traceback.print_exc()
    
    # 9. 出力
    step_num = 9 if args.alpha else 7
    print(f"\n[STEP {step_num}] 結果を保存中...")
    try:
        # 差分CSVを保存
        output_diff_path = Path(args.output_diff)
        output_diff_path.parent.mkdir(parents=True, exist_ok=True)
        df_compare.to_csv(output_diff_path, index=False)
        print(f"  ✓ 差分CSV: {output_diff_path}")
        
        # 最初の不一致日の詳細を保存
        output_mismatch_path = Path(args.output_mismatch)
        if mismatch_detail is not None:
            with open(output_mismatch_path, "w", encoding="utf-8") as f:
                json.dump(mismatch_detail, f, indent=2, ensure_ascii=False, default=str)
            print(f"  ✓ 不一致日詳細: {output_mismatch_path}")
            print(f"\n  最初の不一致日: {mismatch_detail['mismatch_date']}")
            print(f"  差分: {mismatch_detail['diff']:.2e}")
        else:
            # 一致している場合は空のJSONを保存
            with open(output_mismatch_path, "w", encoding="utf-8") as f:
                json.dump({"status": "match", "message": "完全一致"}, f, indent=2, ensure_ascii=False)
            print(f"  ✓ 不一致なし: {output_mismatch_path}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 80)
    print("完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

