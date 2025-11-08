"""
イベントガード
イベント検知モデルを使用して重要な市場イベントを検出
"""

import pandas as pd
from pathlib import Path


class EventGuard:
    """イベントを検知するクラス"""
    
    def __init__(self, models_dir: str = "models/event_guard"):
        self.models_dir = Path(models_dir)
        self.calendar_dir = Path("data/calendar")
    
    def detect_events(self, date: pd.Timestamp) -> list:
        """指定日付のイベントを検出（BOJ/FOMC/CPI等）"""
        pass
    
    def check_event_risk(self, date: pd.Timestamp) -> float:
        """イベントリスクスコアを計算"""
        pass
    
    def should_reduce_position(self, date: pd.Timestamp) -> bool:
        """ポジションを減らすべきか判定"""
        pass

