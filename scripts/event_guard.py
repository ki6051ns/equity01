# scripts/event_guard.py

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class EventGuardConfig:
    """
    EventGuard v0.2 設定クラス
    """

    # ポートフォリオDF側のカラム名
    date_col: str = "trading_date"
    symbol_col: str = "symbol"
    weight_col: str = "weight"

    # 決算カレンダー側
    earnings_date_col: str = "date"
    earnings_symbol_col: str = "symbol"
    earnings_block: bool = True  # Trueなら決算日はその銘柄を0にする

    # マクロイベント側
    macro_date_col: str = "date"
    macro_importance_col: str = "importance"   # 1〜3など
    macro_block_importance: int = 3            # これ以上を「強イベント」とみなす
    macro_risk_factor: float = 0.5             # 強イベント日は全銘柄に掛ける係数

    # VIX側
    vix_date_col: str = "date"
    vix_value_col: str = "close"               # vix['close'] など
    vix_risk_threshold: float = 25.0           # 中リスクのしきい値
    vix_block_threshold: float = 35.0          # フルカットのしきい値
    vix_risk_factor: float = 0.7               # 中リスク時に掛ける係数

    # 出力カラム名
    flag_earnings_col: str = "flag_earnings"
    flag_macro_col: str = "flag_macro"
    flag_vix_col: str = "flag_vix"
    flag_vix_block_col: str = "flag_vix_block"
    guard_factor_col: str = "guard_factor"
    weight_raw_col: str = "weight_raw"


def apply_event_guard(
    df_port: pd.DataFrame,
    config: EventGuardConfig,
    earnings_calendar: Optional[pd.DataFrame] = None,
    macro_calendar: Optional[pd.DataFrame] = None,
    vix: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    EventGuard v0.2 本体。
    - 決算: 該当銘柄はその日の weight を 0 に
    - マクロ: 強イベント日は全銘柄 weight に macro_risk_factor を掛ける
    - VIX: しきい値に応じて weight をさらに絞る or 0 にする

    ※ カレンダーDFが None / empty の場合は何もしない(=素通し)。
    """

    if df_port.empty:
        return df_port

    df = df_port.copy()
    df[config.date_col] = pd.to_datetime(df[config.date_col])

    # --- 生ウェイトのバックアップ ---
    if config.weight_raw_col not in df.columns:
        df[config.weight_raw_col] = df[config.weight_col]

    # --- フラグと guard_factor の初期化（ここが重要） ---
    if config.flag_earnings_col not in df.columns:
        df[config.flag_earnings_col] = False
    if config.flag_macro_col not in df.columns:
        df[config.flag_macro_col] = False
    if config.flag_vix_col not in df.columns:
        df[config.flag_vix_col] = False
    if config.flag_vix_block_col not in df.columns:
        df[config.flag_vix_block_col] = False
    if config.guard_factor_col not in df.columns:
        df[config.guard_factor_col] = 1.0

    # =================================================================
    # 1. 決算イベントガード（銘柄別）
    # =================================================================
    if (
        earnings_calendar is not None
        and not earnings_calendar.empty
        and config.earnings_block
    ):
        earn = earnings_calendar.copy()
        earn[config.earnings_date_col] = pd.to_datetime(earn[config.earnings_date_col])

        # date, symbol のユニーク組み合わせに絞る
        earn_flag = (
            earn[[config.earnings_date_col, config.earnings_symbol_col]]
            .dropna()
            .drop_duplicates()
            .rename(
                columns={
                    config.earnings_date_col: config.date_col,
                    config.earnings_symbol_col: config.symbol_col,
                }
            )
        )

        key_cols = [config.date_col, config.symbol_col]

        df = df.merge(
            earn_flag.assign(**{config.flag_earnings_col: True}),
            on=key_cols,
            how="left",
            suffixes=("", "_earnings_tmp"),
        )

        # merge後の一時列に True が立っているので、それを反映
        tmp_col = config.flag_earnings_col + "_earnings_tmp"
        if tmp_col in df.columns:
            df[config.flag_earnings_col] = df[config.flag_earnings_col] | df[tmp_col].fillna(False)
            df = df.drop(columns=[tmp_col])

        # 決算日の銘柄は guard_factor を 0 に
        df.loc[df[config.flag_earnings_col], config.guard_factor_col] *= 0.0

    # =================================================================
    # 2. マクロイベントガード（日次・全銘柄）
    # =================================================================
    if macro_calendar is not None and not macro_calendar.empty:
        macro = macro_calendar.copy()
        macro[config.macro_date_col] = pd.to_datetime(macro[config.macro_date_col])

        if config.macro_importance_col in macro.columns:
            macro_hi = macro[
                macro[config.macro_importance_col] >= config.macro_block_importance
            ][[config.macro_date_col]].drop_duplicates()
        else:
            macro_hi = macro[[config.macro_date_col]].drop_duplicates()

        macro_hi = macro_hi.rename(columns={config.macro_date_col: config.date_col})

        df = df.merge(
            macro_hi.assign(**{config.flag_macro_col: True}),
            on=[config.date_col],
            how="left",
            suffixes=("", "_macro_tmp"),
        )

        tmp_col = config.flag_macro_col + "_macro_tmp"
        if tmp_col in df.columns:
            df[config.flag_macro_col] = df[config.flag_macro_col] | df[tmp_col].fillna(False)
            df = df.drop(columns=[tmp_col])

        # 強イベント日は guard_factor を縮小
        df.loc[df[config.flag_macro_col], config.guard_factor_col] *= config.macro_risk_factor

    # =================================================================
    # 3. VIXガード（日次・全銘柄）
    # =================================================================
    if vix is not None and not vix.empty:
        v = vix.copy()
        v[config.vix_date_col] = pd.to_datetime(v[config.vix_date_col])
        v = v.rename(columns={config.vix_date_col: config.date_col})

        # VIX値のカラムを決定
        if config.vix_value_col not in v.columns:
            candidate_cols = [c for c in ["close", "adj_close", "Close", "Adj Close"] if c in v.columns]
            if candidate_cols:
                use_col = candidate_cols[0]
            else:
                use_col = None
        else:
            use_col = config.vix_value_col

        if use_col is not None:
            v = v[[config.date_col, use_col]].rename(columns={use_col: config.vix_value_col})

            df = df.merge(v, on=[config.date_col], how="left")

            # 閾値でフラグ
            df[config.flag_vix_col] = df[config.vix_value_col] >= config.vix_risk_threshold
            df[config.flag_vix_block_col] = df[config.vix_value_col] >= config.vix_block_threshold

            # 中リスク: factor *= vix_risk_factor
            df.loc[df[config.flag_vix_col], config.guard_factor_col] *= config.vix_risk_factor
            # 高リスク: 完全カット
            df.loc[df[config.flag_vix_block_col], config.guard_factor_col] = 0.0

    # =================================================================
    # 4. 最終ウェイトの計算
    # =================================================================
    df[config.weight_col] = df[config.weight_raw_col] * df[config.guard_factor_col]

    return df
