"""
equity01 プロジェクトの設定ファイル

Event Guard、ヘッジ、その他の設定を集約。
"""

from pathlib import Path

# ========== Event Guard 関連 ==========

# Event Guard 関連
EVENT_CALENDAR_CSV = "data/events/calendar.csv"   # マクロ・SQ等
EARNINGS_CALENDAR_CSV = "data/events/earnings.csv"  # 決算日

# インバースETF銘柄（あとで実在のティッカーに差し替え）
INVERSE_HEDGE_SYMBOL = "1357.T"  # 例: 日経ダブルインバース 等

# v1.1 のデフォルトヘッジ比率（当面 50%）
DEFAULT_HEDGE_RATIO = 0.5

