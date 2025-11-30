# equity01/scripts/event_guard.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Set

import pandas as pd
import sys

# ---- プロジェクトルートをパスに追加 -----------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import config  # type: ignore


# ---- 設定クラス ---------------------------------------------------------

@dataclass
class EventGuardConfig:
    calendar_csv: str = config.EVENT_CALENDAR_CSV
    earnings_csv: str = config.EARNINGS_CALENDAR_CSV
    inverse_symbol: str = config.INVERSE_HEDGE_SYMBOL
    default_hedge_ratio: float = config.DEFAULT_HEDGE_RATIO


class EventGuard:
    """
    ・マクロ / SQ イベントに応じてヘッジ比率を返す
    ・決算銘柄をユニバースから除外する
    だけを担当する薄いラッパ。
    """

    def __init__(self, cfg: Optional[EventGuardConfig] = None) -> None:
        self.cfg = cfg or EventGuardConfig()
        self._calendar = self._load_calendar(self.cfg.calendar_csv)
        self._earnings = self._load_earnings(self.cfg.earnings_csv)

    # ---------------- 内部ロード処理 ------------------------------------

    @staticmethod
    def _load_calendar(path: str) -> pd.DataFrame:
        try:
            df = pd.read_csv(path, parse_dates=["date"])
        except FileNotFoundError:
            df = pd.DataFrame(
                columns=[
                    "date",
                    "event_type",
                    "subtype",
                    "hedge_ratio",
                    "hedge_days",
                    "comment",
                ]
            )
        if not df.empty:
            df["date"] = df["date"].dt.date
        return df

    @staticmethod
    def _load_earnings(path: str) -> pd.DataFrame:
        try:
            df = pd.read_csv(path, parse_dates=["date"])
        except FileNotFoundError:
            df = pd.DataFrame(columns=["symbol", "date"])
        if not df.empty:
            df["date"] = df["date"].dt.date
        return df

    # ---------------- ヘッジロジック ------------------------------------

    def get_hedge_ratio(self, today: date) -> float:
        """
        今日の「引け」で適用するヘッジ比率を返す。

        calendar.csv の各行について、
        start_date <= today < start_date + hedge_days
        の期間なら有効とみなし、その中で最大の hedge_ratio を返す。
        """
        if self._calendar.empty:
            return 0.0

        ratio = 0.0

        for _, row in self._calendar.iterrows():
            start = row["date"]
            days = int(row.get("hedge_days", 1))
            end = start + timedelta(days=days)

            if start <= today < end:
                r = float(row.get("hedge_ratio", self.cfg.default_hedge_ratio))
                ratio = max(ratio, r)

        return ratio

    # ---------------- 決算除外ロジック ----------------------------------

    def get_excluded_symbols(self, today: date) -> Set[str]:
        """
        今日ユニバースから除外すべき銘柄を返す。
        v1.1 では「決算当日のみ除外」でOK。
        """
        if self._earnings.empty:
            return set()

        mask = self._earnings["date"] == today
        todays = self._earnings.loc[mask, "symbol"]
        return set(todays.astype(str).tolist())

    # ---------------- ユーティリティ ------------------------------------

    @property
    def inverse_symbol(self) -> str:
        return self.cfg.inverse_symbol
