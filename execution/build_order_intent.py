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
    margin_buffer: float = 0.1  # マージン余裕（10%）


def calculate_order_intent(
    target_weights: pd.Series,
    prev_weights: Optional[pd.Series],
    prices: pd.Series,
    config: ExecutionConfig,
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
    notional_delta = config.aum * delta_w * config.leverage_ratio
    
    # order_intentを作成
    df = pd.DataFrame({
        "symbol": all_symbols,
        "prev_weight": prev_w,
        "target_weight": target_w,
        "delta_weight": delta_w,
        "price": price,
        "aum": config.aum,
        "notional_delta": notional_delta,
        "leverage_ratio": config.leverage_ratio,
        "margin_buffer": config.margin_buffer,
    })
    
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
                margin_buffer=config_dict.get("margin_buffer", 0.1),
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
    )
    
    # latest_dateを追加
    df["latest_date"] = latest_date.strftime("%Y-%m-%d")
    
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
        "margin_buffer",
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

