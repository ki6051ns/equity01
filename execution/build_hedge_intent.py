"""
build_hedge_intent.py

βヘッジ用のorder_intentを生成する。
- CFDヘッジ: CFDポートフォリオのβヘッジ
- 現物ヘッジ: 現物ポートフォリオのβヘッジ（インバースETF）
"""

from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
from execution.build_order_intent import ExecutionConfig
from execution.read_latest import read_latest_portfolio
from scripts.tools.lib.data_loader import DataLoader


def build_cfd_hedge_intent(
    cfd_gross_notional: float,
    beta_equity_cfd: float,
    beta_status: str,
    latest_date: pd.Timestamp,
    config: ExecutionConfig,
) -> Optional[pd.DataFrame]:
    """
    CFDヘッジintentを生成する。
    
    Parameters
    ----------
    cfd_gross_notional : float
        CFDポートフォリオの総額
    beta_equity_cfd : float
        CFDポートフォリオのβ
    beta_status : str
        β計算ステータス（"OK" | "STALE" | "FAIL"）
    latest_date : pd.Timestamp
        最新日
    config : ExecutionConfig
        実行設定
    
    Returns
    -------
    pd.DataFrame or None
        CFDヘッジintent（生成できない場合はNone）
    """
    # βステータスがOKでない場合はSKIP
    if beta_status != "OK":
        return None
    
    # ヘッジnotionalを計算
    hedge_notional = cfd_gross_notional * beta_equity_cfd * config.hedge_ratio_cfd
    
    # 最小取引金額未満の場合はSKIP
    if abs(hedge_notional) < config.min_trade_notional_jpy:
        return None
    
    # CFDヘッジintentを作成
    df = pd.DataFrame({
        "latest_date": [latest_date.strftime("%Y-%m-%d")],
        "symbol": [config.cfd_hedge_instrument],
        "prev_weight": [0.0],
        "target_weight": [0.0],
        "delta_weight": [0.0],
        "aum": [config.aum],
        "leverage_ratio": [config.leverage_ratio],
        "notional_delta": [-hedge_notional],  # ショートなので負の値
        "margin_buffer_ratio": [config.margin_buffer_ratio],
        "hedge_type": ["CFD_HEDGE"],
        "notes": [f"CFDヘッジ: beta={beta_equity_cfd:.3f}, ratio={config.hedge_ratio_cfd:.2f}"],
    })
    
    return df


def build_cash_hedge_intent(
    cash_equity_value: float,
    beta_equity_cash: float,
    beta_status: str,
    latest_date: pd.Timestamp,
    config: ExecutionConfig,
    inverse_etf_price: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """
    現物インバースETFヘッジintentを生成する。
    
    Parameters
    ----------
    cash_equity_value : float
        現物ポートフォリオの時価総額
    beta_equity_cash : float
        現物ポートフォリオのβ
    beta_status : str
        β計算ステータス（"OK" | "STALE" | "FAIL"）
    latest_date : pd.Timestamp
        最新日
    config : ExecutionConfig
        実行設定
    inverse_etf_price : float or None
        インバースETFの最新価格（Noneの場合は取得を試みる）
    
    Returns
    -------
    pd.DataFrame or None
        現物ヘッジintent（生成できない場合はNone）
    """
    # βステータスがOKでない場合はSKIP
    if beta_status != "OK":
        return None
    
    # インバースETFの価格を取得
    if inverse_etf_price is None:
        dl = DataLoader(data_dir="data/raw", offline_first=True)
        try:
            etf_prices = dl.load_stock_data(config.cash_inverse_etf_symbol)
            if etf_prices.empty:
                if config.hedge_price_stale_action == "HALT":
                    raise RuntimeError(f"インバースETF価格が取得できません: {config.cash_inverse_etf_symbol}")
                return None
            
            etf_prices["date"] = pd.to_datetime(etf_prices["date"])
            latest_etf_date = etf_prices["date"].max()
            
            # 価格が古い場合の処理
            if latest_etf_date < latest_date - pd.Timedelta(days=2):
                if config.hedge_price_stale_action == "HALT":
                    raise RuntimeError(f"インバースETF価格が古い: {latest_etf_date.date()} < {latest_date.date()}")
                elif config.hedge_price_stale_action == "SKIP":
                    return None
                # USE_LASTの場合は最新の価格を使用
            
            latest_etf_price = etf_prices[etf_prices["date"] == latest_etf_date]["close"].iloc[0]
            if pd.isna(latest_etf_price) or latest_etf_price <= 0:
                if config.hedge_price_stale_action == "HALT":
                    raise RuntimeError(f"インバースETF価格が無効: {latest_etf_price}")
                return None
            
            inverse_etf_price = float(latest_etf_price)
        except Exception as e:
            if config.hedge_price_stale_action == "HALT":
                raise
            return None
    
    # ヘッジnotionalを計算
    hedge_notional = cash_equity_value * beta_equity_cash * config.hedge_ratio_cash
    
    # 最小取引金額未満の場合はSKIP
    if abs(hedge_notional) < config.min_trade_notional_jpy:
        return None
    
    # 株数を計算（1株単位）
    shares = round(hedge_notional / inverse_etf_price)
    
    # 実際のnotionalを再計算（株数ベース）
    actual_notional = shares * inverse_etf_price
    
    # 現物ヘッジintentを作成
    df = pd.DataFrame({
        "latest_date": [latest_date.strftime("%Y-%m-%d")],
        "symbol": [config.cash_inverse_etf_symbol],
        "prev_weight": [0.0],
        "target_weight": [0.0],
        "delta_weight": [0.0],
        "aum": [config.aum],
        "leverage_ratio": [1.0],  # 現物なのでレバレッジなし
        "notional_delta": [actual_notional],  # BUYなので正の値
        "margin_buffer_ratio": [0.0],  # 現物なのでマージンなし
        "hedge_type": ["CASH_HEDGE"],
        "notes": [f"現物ヘッジ: beta={beta_equity_cash:.3f}, ratio={config.hedge_ratio_cash:.2f}, shares={shares}"],
    })
    
    return df


def build_all_hedge_intents(
    latest_date: pd.Timestamp,
    config: Optional[ExecutionConfig] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    すべてのヘッジintentを生成する。
    
    Parameters
    ----------
    latest_date : pd.Timestamp
        最新日
    config : ExecutionConfig or None
        実行設定
    
    Returns
    -------
    (cfd_hedge_intent, cash_hedge_intent)
        CFDヘッジintentと現物ヘッジintent（生成できない場合はNone）
    """
    from execution.build_order_intent import load_config
    
    if config is None:
        config = load_config()
    
    # 最新ポートフォリオを読み込む
    df_latest = read_latest_portfolio()
    
    # β情報を取得
    if "beta_equity_cash" not in df_latest.columns or "beta_equity_cfd" not in df_latest.columns:
        return None, None
    
    beta_equity_cash = df_latest["beta_equity_cash"].iloc[0]
    beta_equity_cfd = df_latest["beta_equity_cfd"].iloc[0]
    beta_status = df_latest["beta_status"].iloc[0]
    
    # CFDポートフォリオの総額を計算（簡易実装：AUM * leverage_ratio）
    cfd_gross_notional = config.aum * config.leverage_ratio
    
    # 現物ポートフォリオの時価総額を計算（簡易実装：AUM）
    cash_equity_value = config.aum
    
    # ヘッジintentを生成
    cfd_hedge = build_cfd_hedge_intent(
        cfd_gross_notional=cfd_gross_notional,
        beta_equity_cfd=beta_equity_cfd,
        beta_status=beta_status,
        latest_date=latest_date,
        config=config,
    )
    
    cash_hedge = build_cash_hedge_intent(
        cash_equity_value=cash_equity_value,
        beta_equity_cash=beta_equity_cash,
        beta_status=beta_status,
        latest_date=latest_date,
        config=config,
    )
    
    return cfd_hedge, cash_hedge

