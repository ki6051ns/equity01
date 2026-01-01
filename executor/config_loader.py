"""
executor/config_loader.py

設定ファイル読み込み（execution/から独立）
"""
from pathlib import Path
from typing import Optional
import json

from executor.models import ExecutionConfig


def load_execution_config(config_path: Optional[Path] = None) -> ExecutionConfig:
    """
    config.jsonからExecutionConfigを読み込む
    
    Parameters
    ----------
    config_path : Path or None
        config.jsonのパス（Noneの場合はexecutor/config.json）
    
    Returns
    -------
    ExecutionConfig
        実行設定
    """
    if config_path is None:
        # executor/config.jsonを優先、なければexecution/config.json（後方互換）
        executor_config = Path("executor/config.json")
        execution_config = Path("execution/config.json")
        
        if executor_config.exists():
            config_path = executor_config
        elif execution_config.exists():
            config_path = execution_config
        else:
            # デフォルト値で返す
            return ExecutionConfig()
    
    if not config_path.exists():
        return ExecutionConfig()
    
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = json.load(f)
    
    # executor/config.json形式（新しい形式）
    if "mode" in config_dict:
        return ExecutionConfig(
            mode=config_dict.get("mode", "DRYRUN_PRE_SUBMIT"),
            stop_before_submit=config_dict.get("stop_before_submit", True),
            aum=config_dict.get("aum", 100_000_000.0),
            leverage_ratio=config_dict.get("leverage_ratio", 1.0),
            cash_buffer_jpy=config_dict.get("cash_buffer_jpy", 200_000.0),
            margin_buffer_ratio=config_dict.get("margin_buffer_ratio", 0.25),
            max_gross_notional_ratio=config_dict.get("max_gross_notional_ratio", 0.30),
            max_symbol_notional_ratio=config_dict.get("max_symbol_notional_ratio", 0.08),
            min_trade_notional_jpy=config_dict.get("min_trade_notional_jpy", 20_000.0),
            stale_price_threshold_days=config_dict.get("precheck", {}).get("stale_price_threshold_days", 2),
            stale_price_action=config_dict.get("precheck", {}).get("stale_price_action", "SKIP"),
            hedge_ratio_cfd=config_dict.get("hedge", {}).get("hedge_ratio_cfd", 1.0),
            hedge_ratio_cash=config_dict.get("hedge", {}).get("hedge_ratio_cash", 1.0),
            cash_inverse_etf_symbol=config_dict.get("hedge", {}).get("cash_inverse_etf_symbol", "XXXX.T"),
            cfd_hedge_instrument=config_dict.get("hedge", {}).get("cfd_hedge_instrument", "TOPIX_CFD_SHORT"),
            lot_size_map=config_dict.get("lot_size_map", {}),
        )
    
    # execution/config.json形式（後方互換）
    else:
        return ExecutionConfig(
            mode="DRYRUN_PRE_SUBMIT",  # デフォルト
            stop_before_submit=True,
            aum=config_dict.get("aum", 100_000_000.0),
            leverage_ratio=config_dict.get("leverage_ratio", 1.0),
            cash_buffer_jpy=config_dict.get("cash_buffer_jpy", 200_000.0),
            margin_buffer_ratio=config_dict.get("margin_buffer_ratio", 0.25),
            max_gross_notional_ratio=config_dict.get("max_gross_notional_ratio", 0.30),
            max_symbol_notional_ratio=config_dict.get("max_symbol_notional_ratio", 0.08),
            min_trade_notional_jpy=config_dict.get("min_trade_notional_jpy", 20_000.0),
            stale_price_threshold_days=2,  # デフォルト
            stale_price_action="SKIP",  # デフォルト
            hedge_ratio_cfd=config_dict.get("hedge", {}).get("hedge_ratio_cfd", 1.0),
            hedge_ratio_cash=config_dict.get("hedge", {}).get("hedge_ratio_cash", 1.0),
            cash_inverse_etf_symbol=config_dict.get("hedge", {}).get("cash_inverse_etf_symbol", "XXXX.T"),
            cfd_hedge_instrument=config_dict.get("hedge", {}).get("cfd_hedge_instrument", "TOPIX_CFD_SHORT"),
            lot_size_map={},
        )

