"""
order_store.py

注文イベントログを追記保存する（jsonl形式）。
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd


class OrderStore:
    """注文イベントログを管理する"""
    
    def __init__(self, output_dir: Path = Path("execution/execution_outputs")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.output_dir / "order_events.jsonl"
    
    def append_event(
        self,
        run_id: str,
        latest_date: str,
        order_key: str,
        symbol: str,
        side: str,
        notional: float,
        price_type: str = "MARKET",
        status: str = "INTENT",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        注文イベントを追記する。
        
        Parameters
        ----------
        run_id : str
            実行ID
        latest_date : str
            最新日（YYYY-MM-DD）
        order_key : str
            注文キー（冪等キー）
        symbol : str
            銘柄コード
        side : str
            売買区分（"BUY" or "SELL"）
        notional : float
            取引金額
        price_type : str
            価格タイプ（"MARKET", "LIMIT"など）
        status : str
            ステータス（INTENT / SUBMITTING / SUBMITTED / ACKED / FILLED / REJECTED / UNKNOWN）
        error_code : str or None
            エラーコード
        error_message : str or None
            エラーメッセージ
        """
        event = {
            "ts": datetime.now().isoformat(),
            "run_id": run_id,
            "latest_date": latest_date,
            "order_key": order_key,
            "symbol": symbol,
            "side": side,
            "notional": notional,
            "price_type": price_type,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
        }
        
        # jsonl形式で追記
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    
    def get_order_status(self, order_key: str) -> Optional[str]:
        """
        指定されたorder_keyの最新ステータスを取得する。
        
        Parameters
        ----------
        order_key : str
            注文キー
        
        Returns
        -------
        str or None
            最新ステータス。存在しない場合はNone
        """
        if not self.events_file.exists():
            return None
        
        # jsonlを読み込んで最新のステータスを取得
        latest_status = None
        
        try:
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("order_key") == order_key:
                        status = event.get("status")
                        if status:
                            latest_status = status
        except Exception:
            pass
        
        return latest_status
    
    def is_order_submitted(self, order_key: str) -> bool:
        """
        指定されたorder_keyが既にSUBMITTED以上かどうかを確認する。
        
        Parameters
        ----------
        order_key : str
            注文キー
        
        Returns
        -------
        bool
            SUBMITTED以上の場合True
        """
        status = self.get_order_status(order_key)
        return status is not None and status in ("SUBMITTED", "ACKED", "FILLED", "REJECTED")
    
    def has_order_intent(self, order_key: str) -> bool:
        """
        指定されたorder_keyが既にINTENTとして記録されているかどうかを確認する。
        （dry-runでの二重防止用）
        
        Parameters
        ----------
        order_key : str
            注文キー
        
        Returns
        -------
        bool
            INTENTが既に存在する場合True
        """
        status = self.get_order_status(order_key)
        return status == "INTENT"
    
    def has_recent_unknown(self, order_key: str, cooldown_sec: float) -> bool:
        """
        指定されたorder_keyに最近のUNKNOWN状態があるかどうかを確認する。
        （クールダウン中の再発注防止用）
        
        Parameters
        ----------
        order_key : str
            注文キー
        cooldown_sec : float
            クールダウン期間（秒）
        
        Returns
        -------
        bool
            クールダウン期間内にUNKNOWNがある場合True
        """
        if not self.events_file.exists():
            return False
        
        from datetime import datetime, timedelta
        
        now = datetime.now()
        cooldown_threshold = now - timedelta(seconds=cooldown_sec)
        
        try:
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("order_key") == order_key and event.get("status") == "UNKNOWN":
                        # tsをパース
                        ts_str = event.get("ts")
                        if ts_str:
                            try:
                                event_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                # タイムゾーンを考慮（簡易版）
                                if event_ts.tzinfo is None:
                                    event_ts = event_ts.replace(tzinfo=None)
                                    if now.tzinfo is None:
                                        # 両方タイムゾーンなしなら比較可能
                                        if event_ts > cooldown_threshold:
                                            return True
                            except Exception:
                                pass
        except Exception:
            pass
        
        return False
    
    def get_events_by_run_id(self, run_id: str) -> List[Dict]:
        """
        指定されたrun_idのイベントを取得する。
        
        Parameters
        ----------
        run_id : str
            実行ID
        
        Returns
        -------
        List[Dict]
            イベントリスト
        """
        if not self.events_file.exists():
            return []
        
        events = []
        try:
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("run_id") == run_id:
                        events.append(event)
        except Exception:
            pass
        
        return events


if __name__ == "__main__":
    # テスト
    store = OrderStore()
    run_id = "test_20250101"
    latest_date = "2025-01-01"
    order_key = "abc123def456"
    
    store.append_event(
        run_id=run_id,
        latest_date=latest_date,
        order_key=order_key,
        symbol="7203.T",
        side="BUY",
        notional=1000000.0,
        status="INTENT",
    )
    
    print(f"is_submitted: {store.is_order_submitted(order_key)}")
    
    store.append_event(
        run_id=run_id,
        latest_date=latest_date,
        order_key=order_key,
        symbol="7203.T",
        side="BUY",
        notional=1000000.0,
        status="SUBMITTED",
    )
    
    print(f"is_submitted: {store.is_order_submitted(order_key)}")

