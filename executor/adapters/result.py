"""
executor/adapters/result.py

Adapter結果型定義
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class AdapterResult:
    """
    アダプター実行結果
    
    PRE_SUBMIT時点の状態を記録（UI反映の証跡）。
    """
    success: bool
    stop_reason: Optional[str] = None  # STOP_BEFORE_SUBMIT等
    ui_reflection_details: Optional[Dict[str, Any]] = None
    """
    UI反映詳細:
    - order_reflected: bool (注文がUIに反映されたか)
    - orders: list[Dict] (各注文のUI反映結果)
    - screenshot_path: Optional[str] (スクリーンショットパス)
    - dom_dump: Optional[str] (DOM dump)
    """
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用の辞書に変換"""
        return {
            "success": self.success,
            "stop_reason": self.stop_reason,
            "ui_reflection_details": self.ui_reflection_details,
            "error_message": self.error_message,
        }

