#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/rebuild_port_ret_from_weights.py

daily_portfolio_guarded + prices から port_ret_cc を再構築するユーティリティ

目的：
- eval_stop_regimes.py で使う port_ret を、horizon_ensemble_variant_cross4.parquet から
  読み込むのではなく、daily_portfolio_guarded + prices から毎回再構築して使用する
- これにより「入力リーク」「別物return」「カレンダー事故」を物理的に封じ込める
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


def rebuild_port_ret_from_weights(
    use_adj_close: bool = True,
    use_weight_lag: bool = True
):
    """
    daily_portfolio_guarded + prices から port_ret_cc を再構築
    
    Parameters
    ----------
    use_adj_close : bool
        Trueならadj_close、Falseならcloseを使用
    use_weight_lag : bool
        Trueなら w[t-1] * r[t]（正）、Falseなら w[t] * r[t]（look-ahead）
    
    Returns
    -------
    dict with keys:
        port_ret : pd.Series
            trade_dateをindexとするポートフォリオリターン（ret_raw[t]）
        contrib_df : pd.DataFrame
            index=trade_date, columns=symbol の寄与行列
        ret_df : pd.DataFrame
            index=trade_date, columns=symbol の銘柄リターン行列
        w_used_df : pd.DataFrame
            index=trade_date, columns=symbol の適用ウェイト行列
    """
    # daily_portfolio_guardedを読み込む
    portfolio_path = DATA_DIR / "daily_portfolio_guarded.parquet"
    
    if not portfolio_path.exists():
        raise FileNotFoundError(
            f"daily_portfolio_guarded.parquetが見つかりません: {portfolio_path}\n"
            "先に scripts/core/build_portfolio.py を実行してください。"
        )
    
    df_weights = pd.read_parquet(portfolio_path)
    
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


if __name__ == "__main__":
    # テスト実行
    print("=" * 80)
    print("=== port_ret_cc 再構築テスト ===")
    print("=" * 80)
    
    try:
        result = rebuild_port_ret_from_weights(use_adj_close=True, use_weight_lag=True)
        port_ret = result["port_ret"]
        print(f"\n✓ 再構築成功: {len(port_ret)} 日分")
        print(f"  期間: {port_ret.index.min().date()} ～ {port_ret.index.max().date()}")
        print(f"  平均リターン: {port_ret.mean():.8f}")
        print(f"  標準偏差: {port_ret.std():.8f}")
        print(f"  寄与行列: {result['contrib_df'].shape}")
        print(f"  リターン行列: {result['ret_df'].shape}")
        print(f"  ウェイト行列: {result['w_used_df'].shape}")
    except Exception as e:
        print(f"\n✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

