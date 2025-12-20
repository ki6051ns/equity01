"""
feature_builder.py

[役割]
- ret / vol / adv を日次クロスセクションで Z 化
- 流動性・ボラティリティに基づく penalty を付与
- 総合スコア (feature_score) を計算して返す

[前提となる入力カラム例]
- date   : 日付 (datetime or string)
- symbol : 銘柄コード / ティッカー
- ret_5d : 5営業日リターン
- ret_20d: 20営業日リターン
- vol_20d: 20営業日リターンの標準偏差（スケールは任意）
- adv_20d: 20営業日平均売買代金
"""

from dataclasses import dataclass, field
from typing import List, Dict
import numpy as np
import pandas as pd


@dataclass
class FeatureBuilderConfig:
    """
    feature_builder のパラメータ設定
    """
    # Z-score を計算する元カラム
    zscore_cols: List[str] = field(
        default_factory=lambda: ["ret_5d", "ret_20d", "vol_20d", "adv_20d"]
    )

    # Z-score を線形結合するときの重み
    # キーは「z_元カラム名」
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "z_ret_5d": 0.4,
            "z_ret_20d": 0.6,
            "z_vol_20d": -0.2,
            "z_adv_20d": 0.1,
        }
    )

    # penalty 関連
    liquidity_adv_col: str = "adv_20d"    # 流動性判定に使う ADV カラム
    low_liq_quantile: float = 0.1         # 下位何％を低流動性とみなすか
    low_liq_penalty: float = -1.0         # 低流動性ペナルティ

    high_vol_z_threshold: float = 2.0     # z_vol がこの値を超えたら高ボラ判定
    high_vol_penalty: float = -0.5        # 高ボラティリティペナルティ

    group_col: str = "date"               # クロスセクション計算単位
    symbol_col: str = "symbol"            # 銘柄識別


def _cross_sectional_zscore(
    df: pd.DataFrame, col: str, group_col: str
) -> pd.Series:
    """
    クロスセクション Z-score を計算するユーティリティ関数
    """
    def _z(x: pd.Series) -> pd.Series:
        if x.std(ddof=0) == 0:
            # すべて同じ値の場合は 0 に揃える
            return pd.Series(0.0, index=x.index)
        return (x - x.mean()) / x.std(ddof=0)

    return df.groupby(group_col)[col].transform(_z)


def build_feature_matrix(
    df: pd.DataFrame, config: FeatureBuilderConfig
) -> pd.DataFrame:
    """
    メイン関数：
    - Z-score 付与
    - penalty 付与
    - 総合スコア feature_score 計算

    Parameters
    ----------
    df : pd.DataFrame
        入力データ（長い形式: date, symbol が行方向に並ぶ）
    config : FeatureBuilderConfig
        設定

    Returns
    -------
    pd.DataFrame
        入力 df に以下を付与したもの:
        - z_* カラム
        - pen_liquidity, pen_vol, penalty_total
        - feature_raw (ペナルティ前のスコア)
        - feature_score (ペナルティ適用後スコア)
    """
    df = df.copy()

    # --- 1. Z-score の計算 ---
    for col in config.zscore_cols:
        if col not in df.columns:
            raise KeyError(f"必要なカラムがありません: {col}")

        zcol = f"z_{col}"
        df[zcol] = _cross_sectional_zscore(df, col, config.group_col)

    # ---- Zスコアのクリップ（±3σ） ----
    z_cols = ["z_ret_5d", "z_ret_20d", "z_vol_20d", "z_adv_20d"]
    for c in z_cols:
        if c in df.columns:
            # 日次クロスセクションで ±3σ にクリップ（極端値で暴れないように）
            df[c] = df.groupby("date")[c].transform(lambda s: s.clip(-3.0, 3.0))

    # --- 2. 流動性ペナルティ (ADVの下位20%) ---
    # 日次クロスセクションで下位20%を "低流動性" とみなす
    adv_q = df.groupby("date")["adv_20d"].transform(
        lambda s: s.quantile(0.2)
    )
    df["pen_liquidity"] = 0.0
    df.loc[df["adv_20d"] < adv_q, "pen_liquidity"] = -0.5

    # --- 3. ボラペナルティ (VOLの上位20%) ---
    vol_q = df.groupby("date")["vol_20d"].transform(
        lambda s: s.quantile(0.8)
    )
    df["pen_vol"] = 0.0
    df.loc[df["vol_20d"] > vol_q, "pen_vol"] = -0.5

    # --- 4. トータルペナルティ ---
    df["penalty_total"] = df["pen_liquidity"] + df["pen_vol"]
    df["penalty_total"] = df["penalty_total"].clip(-1.0, 0.0)

    # --- 5. モメンタム合成 (v1.1) ---
    w_short = 0.6   # 5日リターン Z の重み
    w_medium = 0.4  # 20日リターン Z の重み

    df["feature_raw"] = (
        w_short * df["z_ret_5d"]
        + w_medium * df["z_ret_20d"]
    )

    # --- 6. ペナルティを反映した最終スコア ---
    df["feature_score"] = df["feature_raw"] + df["penalty_total"]

    return df
