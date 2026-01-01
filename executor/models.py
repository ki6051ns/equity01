"""
executor/models.py

Intent-based execution models.
OrderIntent / HedgeIntent / ExecutionConfig / RunLog のスキーマ定義。
"""
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any, List
from datetime import date


@dataclass
class ExecutionConfig:
    """
    実行設定（ExecutionConfig）
    
    executor実行に必要な設定を集約。
    """
    mode: Literal["DRYRUN_PRE_SUBMIT", "LIVE_SUBMIT"] = "DRYRUN_PRE_SUBMIT"
    stop_before_submit: bool = True
    
    # AUM・レバレッジ
    aum: float = 100_000_000.0  # 1億円
    leverage_ratio: float = 1.0  # レバレッジ（1.0 = ノンレバ）
    
    # 余力・バッファ
    cash_buffer_jpy: float = 200_000.0  # 現金バッファ（常に現金で残す）
    margin_buffer_ratio: float = 0.25  # マージン余裕比率（25%）
    
    # 取引制約
    max_gross_notional_ratio: float = 0.30  # AUMに対する当日売買代金の上限
    max_symbol_notional_ratio: float = 0.08  # 1銘柄の当日増分上限
    min_trade_notional_jpy: float = 20_000.0  # 最小取引金額
    
    # 価格鮮度
    stale_price_threshold_days: int = 2  # 許容遅延日数
    stale_price_action: Literal["HALT", "SKIP", "USE_LAST"] = "SKIP"
    
    # ヘッジ設定
    hedge_ratio_cfd: float = 1.0
    hedge_ratio_cash: float = 1.0
    cash_inverse_etf_symbol: str = "XXXX.T"  # 現物インバースETFシンボル
    cfd_hedge_instrument: str = "TOPIX_CFD_SHORT"  # CFDヘッジ商品
    
    # 単元・lot設定（Dict[symbol, lot_size]）
    lot_size_map: Dict[str, int] = field(default_factory=dict)  # デフォルトは空（1株単位）


@dataclass
class OrderIntent:
    """
    注文意図（OrderIntent）
    
    リバランス・ヘッジ・STOPに基づく注文意図を表現。
    数量（qty）はexecutor側で確定（現実制約を考慮）。
    """
    date: date
    account: Literal["cash", "cfd"]
    symbol: str
    side: Literal["buy", "sell"]
    qty: int  # executor側で確定（単元・価格・余力から計算）
    price_ref: Literal["last", "close"]  # 価格参照方法
    reason: Literal["rebalance", "hedge", "stop"]
    
    # 制約条件（executor側で検証・適用）
    constraints: Dict[str, Any]
    """
    制約辞書:
    - min_cash: float (現物の場合、最小現金残高)
    - max_leverage: float (CFDの場合、最大レバレッジ)
    """
    
    # メタデータ（ログ・監査用）
    notional: float  # qty * price_ref の想定額
    order_key: str  # 冪等性確保のためのdeterministic key（date|account|symbol|side|qty|price_ref）
    prev_weight: Optional[float] = None
    target_weight: Optional[float] = None
    delta_weight: Optional[float] = None
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用の辞書に変換（パスワードは除外）"""
        return {
            "date": self.date.isoformat(),
            "account": self.account,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "price_ref": self.price_ref,
            "reason": self.reason,
            "constraints": self.constraints,
            "notional": self.notional,
            "order_key": self.order_key,
            "prev_weight": self.prev_weight,
            "target_weight": self.target_weight,
            "delta_weight": self.delta_weight,
            "notes": self.notes,
        }


@dataclass
class HedgeIntent:
    """
    ヘッジ意図（HedgeIntent）
    
    βヘッジ用の注文意図（1306 / 1569はexecutorでのみ使用）。
    coreには絶対に戻さない。
    """
    date: date
    hedge_type: Literal["inverseETF", "CFD"]
    ref_beta: float  # t-1時点のβ
    target_notional: float  # ヘッジ対象のnotional
    hedge_ratio: float  # ヘッジ比率（外挿OK）
    price_ref: Literal["last", "close"]
    
    # 具体的な注文パラメータ（executor側で確定）
    symbol: str
    side: Literal["buy", "sell"]
    qty: Optional[int] = None  # 現物の場合のみ
    
    # メタデータ
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用の辞書に変換"""
        return {
            "date": self.date.isoformat(),
            "hedge_type": self.hedge_type,
            "ref_beta": self.ref_beta,
            "target_notional": self.target_notional,
            "hedge_ratio": self.hedge_ratio,
            "price_ref": self.price_ref,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "notes": self.notes,
        }


@dataclass
class RunLog:
    """
    実行ログ（RunLog）
    
    1 run = 1 ファイル: executor_runs/runs/run_{run_id}.json
    
    PRE_SUBMIT時点の状態を完全に記録（判断根拠＝監査証跡）。
    """
    run_id: str
    created_at: str  # ISO形式のタイムスタンプ
    latest_date: date
    mode: Literal["DRYRUN_PRE_SUBMIT", "LIVE_SUBMIT"]
    
    # 入力ファイルhash（再現性確保）
    inputs_hash: Optional[str] = None  # daily_portfolio_guarded.parquetのhash
    
    # 冪等性確認用hash
    intent_hash: Optional[str] = None  # order_intentsを正規化してsha256（冪等性確認用）
    
    # スナップショット（余力・価格鮮度等）
    snapshots: Dict[str, Any] = field(default_factory=dict)
    """
    スナップショット辞書:
    - cash_available: float (現物買付余力)
    - margin_available: float (CFD利用可能証拠金)
    - margin_maintenance_ratio: float (維持率)
    - price_freshness: Dict[symbol, Dict] (価格鮮度チェック結果)
    """
    
    # 実行結果
    order_intents: List[Dict[str, Any]] = field(default_factory=list)  # OrderIntent.to_dict()のリスト
    hedge_intents: List[Dict[str, Any]] = field(default_factory=list)  # HedgeIntent.to_dict()のリスト
    
    # 結果
    results: Dict[str, Any] = field(default_factory=dict)
    """
    結果辞書:
    - precheck_passed: bool (事前チェック通過したか)
    - ui_reflected: bool (PRE_SUBMIT時にUI反映成功したか)
    - ui_reflection_details: Dict (詳細情報)
    - stop_reason: str (停止理由: STOP_BEFORE_SUBMIT等)
    - errors: list[Dict] (エラー情報のリスト)
    """
    
    def to_dict(self) -> Dict[str, Any]:
        """
        JSONシリアライズ用の辞書に変換
        
        Warning
        -------
        パスワードは絶対に含めない
        """
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "latest_date": self.latest_date.isoformat(),
            "mode": self.mode,
            "inputs_hash": self.inputs_hash,
            "intent_hash": self.intent_hash,
            "snapshots": self.snapshots,
            "order_intents": self.order_intents,
            "hedge_intents": self.hedge_intents,
            "results": self.results,
        }

