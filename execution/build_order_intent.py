"""
build_order_intent.py

Δweightからnotionalを計算してorder_intentを構築する。
"""
from pathlib import Path
import json
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class ExecutionConfig:
    """実行設定"""
    aum: float = 100_000_000.0  # 1億円
    leverage_ratio: float = 1.0  # レバレッジ（1.0 = ノンレバ）
    margin_buffer_ratio: float = 0.25  # マージン余裕比率（25%）
    cash_buffer_jpy: float = 200_000.0  # 現金バッファ（常に現金で残す）
    max_gross_notional_ratio: float = 0.30  # AUMに対する当日売買代金の上限
    max_symbol_notional_ratio: float = 0.08  # 1銘柄の当日増分上限
    min_trade_notional_jpy: float = 20_000.0  # 最小取引金額
    retry_max: int = 3  # リトライ最大回数
    retry_backoff_sec: float = 2.0  # リトライバックオフ（秒）
    timeout_sec: float = 10.0  # タイムアウト（秒）
    dry_run: bool = True  # dry-runモード
    unknown_cooldown_sec: float = 1800.0  # UNKNOWNクールダウン（秒、30分）
    unknown_action: str = "SKIP"  # UNKNOWN時の動作（"SKIP" or "HALT"）
    unknown_scope: str = "order_key"  # UNKNOWNスコープ（"order_key" or "latest_date"）
    # βヘッジ設定
    hedge_ratio_cfd: float = 1.0  # CFDヘッジ比率
    hedge_ratio_cash: float = 1.0  # 現物ヘッジ比率
    hedge_price_stale_action: str = "SKIP"  # ヘッジ価格が古い場合の動作（"SKIP" | "HALT" | "USE_LAST"）
    cash_inverse_etf_symbol: str = "XXXX.T"  # 現物インバースETFシンボル
    cfd_hedge_instrument: str = "TOPIX_CFD_SHORT"  # CFDヘッジ商品
    
    # 後方互換性のため
    @property
    def margin_buffer(self) -> float:
        """後方互換性のため（margin_buffer_ratioに置き換え）"""
        return self.margin_buffer_ratio


def calculate_order_intent(
    target_weights: pd.Series,
    prev_weights: Optional[pd.Series],
    prices: pd.Series,
    config: ExecutionConfig,
    available_cash: Optional[float] = None,
    available_margin: Optional[float] = None,
) -> pd.DataFrame:
    """
    ターゲットウェイトと前日ウェイトからorder_intentを計算する。
    
    Parameters
    ----------
    target_weights : pd.Series
        ターゲットウェイト（symbol -> weight）
    prev_weights : pd.Series or None
        前日ウェイト（symbol -> weight）。初回実行時はNone
    prices : pd.Series
        現在価格（symbol -> price）
    config : ExecutionConfig
        実行設定
    
    Returns
    -------
    pd.DataFrame
        order_intent（symbol, prev_weight, target_weight, delta_weight,
                     aum, notional_delta, leverage_ratio, margin_buffer, notes）
    """
    # 前日ウェイトが無い場合は0とみなす
    if prev_weights is None:
        prev_weights = pd.Series(0.0, index=target_weights.index)
    
    # 全銘柄のユニオンを取得
    all_symbols = target_weights.index.union(prev_weights.index).union(prices.index)
    all_symbols = all_symbols.sort_values()
    
    # 各銘柄のウェイトを取得（存在しない場合は0）
    prev_w = prev_weights.reindex(all_symbols, fill_value=0.0)
    target_w = target_weights.reindex(all_symbols, fill_value=0.0)
    price = prices.reindex(all_symbols, fill_value=0.0)
    
    # delta_weightを計算
    delta_w = target_w - prev_w
    
    # notional_deltaを計算（= aum * delta_weight * leverage）
    # まずはDataFrameとして作成
    df_base = pd.DataFrame({
        "symbol": all_symbols,
        "prev_weight": prev_w,
        "target_weight": target_w,
        "delta_weight": delta_w,
        "price": price,
    })
    
    notional_delta = config.aum * delta_w * config.leverage_ratio
    
    # 3-1) 共通：上限制約でクリップ
    gross_notional = notional_delta.abs().sum()
    gross_notional_cap = config.aum * config.max_gross_notional_ratio
    
    if gross_notional > gross_notional_cap:
        scale = gross_notional_cap / gross_notional
        notional_delta = notional_delta * scale
    
    # 3-2) 現物（買付余力）
    # available_cashが指定されていない場合は推定
    if available_cash is None:
        available_cash = config.aum - config.cash_buffer_jpy
    
    buy_notional = notional_delta[notional_delta > 0].sum()
    if buy_notional > available_cash:
        # BUY側を縮小
        buy_scale = available_cash / buy_notional
        notional_delta = notional_delta.apply(lambda x: x * buy_scale if x > 0 else x)
    
    # 3-3) CFD（必要証拠金＋バッファ）
    if config.leverage_ratio > 1.0:
        gross_buy_notional = notional_delta[notional_delta > 0].abs().sum()
        req_margin_simple = gross_buy_notional / config.leverage_ratio
        req_margin_with_buffer = req_margin_simple * (1 + config.margin_buffer_ratio)
        
        # available_marginが指定されていない場合は推定
        if available_margin is None:
            available_margin = config.aum - config.cash_buffer_jpy
        
        if req_margin_with_buffer > available_margin:
            # notionalを縮小
            margin_scale = available_margin / req_margin_with_buffer
            notional_delta = notional_delta * margin_scale
    
    # 銘柄別上限チェック
    max_symbol_notional = config.aum * config.max_symbol_notional_ratio
    notional_delta = notional_delta.apply(lambda x: max(-max_symbol_notional, min(max_symbol_notional, x)))
    
    # DataFrameを作成（notional_deltaは既に調整済み）
    df = df_base.copy()
    df["aum"] = config.aum
    df["notional_delta"] = notional_delta
    df["leverage_ratio"] = config.leverage_ratio
    df["margin_buffer_ratio"] = config.margin_buffer_ratio
    
    # 最小取引金額以下を除外
    df = df[df["notional_delta"].abs() >= config.min_trade_notional_jpy].copy()
    
    # notesを追加（丸めや欠損の理由）
    notes = []
    for idx, row in df.iterrows():
        note_parts = []
        if abs(row["delta_weight"]) < 0.001:  # 0.1%未満は無視
            note_parts.append("delta_weight < 0.1%")
        if row["price"] == 0.0:
            note_parts.append("price missing")
        if row["target_weight"] == 0.0 and row["prev_weight"] > 0.0:
            note_parts.append("exit")
        elif row["target_weight"] > 0.0 and row["prev_weight"] == 0.0:
            note_parts.append("enter")
        notes.append("; ".join(note_parts) if note_parts else "")
    
    df["notes"] = notes
    
    # delta_weightが0に近い行を除外（オプション）
    df = df[df["delta_weight"].abs() >= 0.001].copy()
    
    return df


def load_config(config_path: Path = Path("execution/config.json")) -> ExecutionConfig:
    """
    config.jsonから設定を読み込む。
    
    Parameters
    ----------
    config_path : Path
        config.jsonのパス
    
    Returns
    -------
    ExecutionConfig
        実行設定
    """
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
            return ExecutionConfig(
                aum=config_dict.get("aum", 100_000_000.0),
                leverage_ratio=config_dict.get("leverage_ratio", 1.0),
                margin_buffer_ratio=config_dict.get("margin_buffer_ratio", 0.25),
                cash_buffer_jpy=config_dict.get("cash_buffer_jpy", 200_000.0),
                max_gross_notional_ratio=config_dict.get("max_gross_notional_ratio", 0.30),
                max_symbol_notional_ratio=config_dict.get("max_symbol_notional_ratio", 0.08),
                min_trade_notional_jpy=config_dict.get("min_trade_notional_jpy", 20_000.0),
                retry_max=config_dict.get("retry_max", 3),
                retry_backoff_sec=config_dict.get("retry_backoff_sec", 2.0),
                timeout_sec=config_dict.get("timeout_sec", 10.0),
                dry_run=config_dict.get("dry_run", True),
                unknown_cooldown_sec=config_dict.get("unknown_cooldown_sec", 1800.0),
                unknown_action=config_dict.get("unknown_action", "SKIP"),
                unknown_scope=config_dict.get("unknown_scope", "order_key"),
                # βヘッジ設定
                hedge_ratio_cfd=config_dict.get("hedge", {}).get("hedge_ratio_cfd", 1.0),
                hedge_ratio_cash=config_dict.get("hedge", {}).get("hedge_ratio_cash", 1.0),
                hedge_price_stale_action=config_dict.get("hedge", {}).get("hedge_price_stale_action", "SKIP"),
                cash_inverse_etf_symbol=config_dict.get("hedge", {}).get("cash_inverse_etf_symbol", "XXXX.T"),
                cfd_hedge_instrument=config_dict.get("hedge", {}).get("cfd_hedge_instrument", "TOPIX_CFD_SHORT"),
            )
    else:
        # デフォルト値
        return ExecutionConfig()


def build_order_intent(
    target_weights: pd.Series,
    prev_weights: Optional[pd.Series],
    prices: pd.Series,
    latest_date: pd.Timestamp,
    config: Optional[ExecutionConfig] = None,
    available_cash: Optional[float] = None,
    available_margin: Optional[float] = None,
) -> pd.DataFrame:
    """
    order_intentを構築する。
    
    Parameters
    ----------
    target_weights : pd.Series
        ターゲットウェイト（symbol -> weight）
    prev_weights : pd.Series or None
        前日ウェイト（symbol -> weight）。初回実行時はNone
    prices : pd.Series
        現在価格（symbol -> price）
    latest_date : pd.Timestamp
        最新日
    config : ExecutionConfig or None
        実行設定。Noneの場合はconfig.jsonから読み込む
    
    Returns
    -------
    pd.DataFrame
        order_intent（latest_date, symbol, prev_weight, target_weight, delta_weight,
                     aum, leverage_ratio, notional_delta, margin_buffer, notes）
    """
    if config is None:
        config = load_config()
    
    df = calculate_order_intent(
        target_weights=target_weights,
        prev_weights=prev_weights,
        prices=prices,
        config=config,
        available_cash=available_cash,
        available_margin=available_margin,
    )
    
    # latest_dateを追加
    df["latest_date"] = latest_date.strftime("%Y-%m-%d")
    
    # hedge_type列を追加（デフォルトはNORMAL）
    df["hedge_type"] = "NORMAL"
    
    # 列の順序を整理
    cols = [
        "latest_date",
        "symbol",
        "prev_weight",
        "target_weight",
        "delta_weight",
        "aum",
        "leverage_ratio",
        "notional_delta",
        "margin_buffer_ratio",
        "hedge_type",
        "notes",
    ]
    # 存在する列だけ選択
    cols = [c for c in cols if c in df.columns]
    df = df[cols]
    
    return df


if __name__ == "__main__":
    # テスト
    target = pd.Series({"7203.T": 0.1, "6758.T": 0.2, "9984.T": 0.15})
    prev = pd.Series({"7203.T": 0.15, "6758.T": 0.2})
    prices = pd.Series({"7203.T": 10000.0, "6758.T": 5000.0, "9984.T": 8000.0})
    
    config = load_config()
    df = build_order_intent(
        target_weights=target,
        prev_weights=prev,
        prices=prices,
        latest_date=pd.Timestamp("2025-01-01"),
        config=config,
    )
    print(df)

