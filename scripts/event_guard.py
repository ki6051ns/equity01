# scripts/event_guard.py

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class EventGuardConfig:
    # カラム名
    date_col: str = "date"
    symbol_col: str = "symbol"
    weight_col: str = "weight"

    # 決算日前後何日ブロックするか
    pre_earnings_days: int = 1
    post_earnings_days: int = 1

    # マクロイベント・VIXスパイク時のウェイト
    macro_weight: float = 0.5   # 例：FOMC / 日銀 / CPI
    vix_threshold: float = 0.15 # VIX前日比+15%でスパイク判定
    vix_weight: float = 0.7     # VIXスパイク時の縮小比率


def _expand_earnings_window(
    earnings: pd.DataFrame,
    cfg: EventGuardConfig,
) -> set:
    """
    earnings: [date, symbol] を前提として、
    決算日±N日の (symbol, date) セットを作る。
    """
    e = earnings[[cfg.date_col, cfg.symbol_col]].copy()
    e[cfg.date_col] = pd.to_datetime(e[cfg.date_col])

    rows = []
    for offset in range(-cfg.pre_earnings_days, cfg.post_earnings_days + 1):
        tmp = e.copy()
        tmp[cfg.date_col] = tmp[cfg.date_col] + pd.Timedelta(days=offset)
        tmp["_offset"] = offset
        rows.append(tmp)

    expanded = pd.concat(rows, ignore_index=True)
    expanded["_key"] = (
        expanded[cfg.symbol_col].astype(str)
        + "|"
        + expanded[cfg.date_col].dt.strftime("%Y-%m-%d")
    )
    return set(expanded["_key"])


def _compute_vix_flags(
    vix: pd.DataFrame,
    cfg: EventGuardConfig,
) -> pd.DataFrame:
    """
    vix: [date, close] 想定。
    VIX前日比が閾値以上の日をフラグ化。
    """
    v = vix.copy()
    v[cfg.date_col] = pd.to_datetime(v[cfg.date_col])
    v = v.sort_values(cfg.date_col)

    v["vix_ret"] = v["close"].pct_change()
    v["flag_vix_spike"] = v["vix_ret"] >= cfg.vix_threshold
    return v[[cfg.date_col, "flag_vix_spike"]]


def apply_event_guard(
    df_port: pd.DataFrame,
    cfg: EventGuardConfig,
    earnings_calendar: Optional[pd.DataFrame] = None,  # [date, symbol]
    macro_calendar: Optional[pd.DataFrame] = None,     # [date, impact(=high/med/low)]
    vix: Optional[pd.DataFrame] = None,                # [date, close]
) -> pd.DataFrame:
    """
    ポートフォリオ（build_daily_portfolio の出力）に対して
    - 決算前後ブロック
    - マクロイベント時ウェイト縮小
    - VIXスパイク時ウェイト縮小
    を掛ける最小版 EventGuard。

    df_port 必須カラム:
      - date_col, symbol_col
      - weight_col（無くてもOK、その場合はフラグのみ付与）
    """
    df = df_port.copy()
    dcol = cfg.date_col
    scol = cfg.symbol_col

    df[dcol] = pd.to_datetime(df[dcol])

    # 初期フラグ
    df["flag_earnings_window"] = False
    df["flag_macro"] = False
    df["flag_vix_spike"] = False
    df["event_weight_multiplier"] = 1.0

    # 1) 決算前後ブロック
    if earnings_calendar is not None and not earnings_calendar.empty:
        e = earnings_calendar[[dcol, scol]].copy()
        e[dcol] = pd.to_datetime(e[dcol])

        keyset = _expand_earnings_window(e, cfg)
        keys = df[scol].astype(str) + "|" + df[dcol].dt.strftime("%Y-%m-%d")
        df["flag_earnings_window"] = keys.isin(keyset)

    # 2) マクロイベント（impact == "high" を想定）
    if macro_calendar is not None and not macro_calendar.empty:
        m = macro_calendar.copy()
        m[dcol] = pd.to_datetime(m[dcol])
        high_days = set(
            m[m.get("impact", "high") == "high"][dcol].dt.strftime("%Y-%m-%d")
        )
        df["flag_macro"] = df[dcol].dt.strftime("%Y-%m-%d").isin(high_days)

    # 3) VIXスパイク
    if vix is not None and not vix.empty:
        vix_flags = _compute_vix_flags(vix, cfg)
        df = df.merge(vix_flags, on=dcol, how="left")
        df["flag_vix_spike"] = df["flag_vix_spike"].fillna(False)

    # 4) event_weight_multiplier の計算
    mult = np.ones(len(df))

    # マクロイベントで 0.5 倍
    mult = np.where(df["flag_macro"], mult * cfg.macro_weight, mult)

    # VIXスパイクで 0.7 倍
    mult = np.where(df["flag_vix_spike"], mult * cfg.vix_weight, mult)

    # 決算前後は完全ブロック（ウェイト0）
    mult = np.where(df["flag_earnings_window"], 0.0, mult)

    df["event_weight_multiplier"] = mult

    # 5) weight 列があれば上書き
    if cfg.weight_col in df.columns:
        df[cfg.weight_col] = df[cfg.weight_col] * df["event_weight_multiplier"]

    return df
