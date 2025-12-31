"""
β計算モジュール

ポートフォリオ全体のβを計算する（簡易実装）
- ポートフォリオのリターンとベンチマーク（1306.T）のリターンからβを計算
- 現物ポートフォリオとCFDポートフォリオを区別（現時点では同じ計算）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Optional
from scripts.tools.lib.data_loader import DataLoader


def calculate_portfolio_beta(
    portfolio_df: pd.DataFrame,
    benchmark_symbol: str = "1306.T",
    lookback_days: int = 60,
    min_periods: int = 20,
) -> Tuple[float, float, str, Optional[pd.Timestamp]]:
    """
    ポートフォリオ全体のβを計算
    
    Args:
        portfolio_df: ポートフォリオDataFrame（date, symbol, weight列が必要）
        benchmark_symbol: ベンチマークシンボル（デフォルト: 1306.T）
        lookback_days: 計算に使用する過去日数
        min_periods: 最小データポイント数
    
    Returns:
        (beta_equity_cash, beta_equity_cfd, beta_status, beta_ref_date)
        - beta_equity_cash: 現物ポートフォリオのβ
        - beta_equity_cfd: CFDポートフォリオのβ（現時点では同じ値）
        - beta_status: "OK" | "STALE" | "FAIL"
        - beta_ref_date: ベンチマークの最新日付
    """
    try:
        # データローダーを初期化
        dl = DataLoader(data_dir="data/raw", offline_first=True)
        
        # ベンチマーク価格を取得
        benchmark_prices = dl.load_stock_data(benchmark_symbol)
        if benchmark_prices.empty:
            return 0.0, 0.0, "FAIL", None
        
        benchmark_prices["date"] = pd.to_datetime(benchmark_prices["date"])
        benchmark_prices = benchmark_prices.sort_values("date")
        benchmark_prices["ret_1d"] = benchmark_prices["close"].pct_change()
        
        # ポートフォリオの最新日付を取得
        portfolio_df = portfolio_df.copy()
        portfolio_df["date"] = pd.to_datetime(portfolio_df["date"])
        latest_date = portfolio_df["date"].max()
        
        # ベンチマークの最新日付を確認
        benchmark_latest = benchmark_prices["date"].max()
        beta_ref_date = benchmark_latest
        
        # ベンチマークが古い場合はSTALE
        if benchmark_latest < latest_date - pd.Timedelta(days=2):
            return 0.0, 0.0, "STALE", beta_ref_date
        
        # ポートフォリオのリターンを計算
        # 簡易実装：個別銘柄のリターンをweightで加重平均
        portfolio_returns = []
        
        # 価格データを取得（load_prices関数を使用）
        from scripts.tools.lib.data_loader import load_prices
        prices = load_prices()
        prices["date"] = pd.to_datetime(prices["date"])
        
        # 最新日のポートフォリオ銘柄を取得
        latest_portfolio = portfolio_df[portfolio_df["date"] == latest_date].copy()
        
        if latest_portfolio.empty:
            return 0.0, 0.0, "FAIL", beta_ref_date
        
        # 各銘柄のリターンを計算
        symbols = latest_portfolio["symbol"].unique()
        symbol_returns = {}
        
        for symbol in symbols:
            symbol_prices = prices[prices["symbol"] == symbol].copy()
            if symbol_prices.empty:
                continue
            
            symbol_prices = symbol_prices.sort_values("date")
            symbol_prices["ret_1d"] = symbol_prices["close"].pct_change()
            symbol_returns[symbol] = symbol_prices[["date", "ret_1d"]].copy()
        
        if not symbol_returns:
            return 0.0, 0.0, "FAIL", beta_ref_date
        
        # 日付でマージしてポートフォリオリターンを計算
        # 簡易実装：共通の日付範囲でリターンを計算
        all_dates = set(benchmark_prices["date"].values)
        for symbol_ret_df in symbol_returns.values():
            all_dates = all_dates.intersection(set(symbol_ret_df["date"].values))
        
        all_dates = sorted([d for d in all_dates if d <= latest_date])[-lookback_days:]
        
        if len(all_dates) < min_periods:
            return 0.0, 0.0, "FAIL", beta_ref_date
        
        portfolio_ret_series = []
        benchmark_ret_series = []
        
        for date_val in all_dates:
            # その日のポートフォリオリターン（weight加重平均）
            port_ret = 0.0
            total_weight = 0.0
            
            for symbol in symbols:
                if symbol not in symbol_returns:
                    continue
                symbol_ret_df = symbol_returns[symbol]
                symbol_ret_on_date = symbol_ret_df[symbol_ret_df["date"] == date_val]
                if symbol_ret_on_date.empty:
                    continue
                
                ret_val = symbol_ret_on_date["ret_1d"].iloc[0]
                weight_df = latest_portfolio[latest_portfolio["symbol"] == symbol]
                weight = weight_df["weight"].iloc[0] if not weight_df.empty else 0.0
                
                if pd.notna(ret_val) and pd.notna(weight):
                    port_ret += ret_val * weight
                    total_weight += weight
            
            if total_weight > 0:
                port_ret = port_ret / total_weight
                bench_ret_df = benchmark_prices[benchmark_prices["date"] == date_val]
                if not bench_ret_df.empty:
                    bench_ret = bench_ret_df["ret_1d"].iloc[0]
                    
                    if pd.notna(port_ret) and pd.notna(bench_ret):
                        portfolio_ret_series.append(port_ret)
                        benchmark_ret_series.append(bench_ret)
        
        if len(portfolio_ret_series) < min_periods:
            return 0.0, 0.0, "FAIL", beta_ref_date
        
        # βを計算（共分散/分散）
        portfolio_ret = np.array(portfolio_ret_series)
        benchmark_ret = np.array(benchmark_ret_series)
        
        cov = np.cov(portfolio_ret, benchmark_ret)[0, 1]
        var = np.var(benchmark_ret)
        
        if var > 0:
            beta = cov / var
        else:
            beta = 0.0
        
        # 現物とCFDは現時点では同じ値（将来分離可能）
        beta_equity_cash = float(beta)
        beta_equity_cfd = float(beta)
        
        return beta_equity_cash, beta_equity_cfd, "OK", beta_ref_date
    
    except Exception as e:
        import logging
        logging.warning(f"beta_calculator: β計算エラー: {e}")
        return 0.0, 0.0, "FAIL", None

