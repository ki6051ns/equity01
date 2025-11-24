"""
scoring_engine.py

役割：
- feature_builder で作った feature_score を元に
  - Large / Mid / Small の size bucket を付与
  - bucket 内で Z-score を取り直し
  - 各 bucket から均等に銘柄をピック
  - 日次のポートフォリオ候補テーブルを返す
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional
import numpy as np
import pandas as pd

SizeBucket = Literal["Large", "Mid", "Small"]


@dataclass
class ScoringEngineConfig:
    # bucket を格納するカラム名
    size_bucket_col: str = "size_bucket"

    # 流動性の代理指標（なければ market_cap などに差し替え）
    liquidity_col: str = "adv_20d"

    # 1日あたりの最大保有銘柄数（全体）
    max_names_per_day: int = 30

    # Large / Mid / Small の比率（合計1になるように）
    size_bucket_weights: dict = field(
        default_factory=lambda: {
            "Large": 1 / 3,
            "Mid": 1 / 3,
            "Small": 1 / 3,
        }
    )

    # bucket 内で銘柄を選ぶ際の最小スコア閾値
    min_score_threshold: float = -np.inf  # とりあえず制約なし

    # 最終的に weight をどう計算するか
    # "equal": 同一重み, "score": feature_score 比例
    weighting_scheme: Literal["equal", "score"] = "equal"

    # 日次グルーピングに使うカラム
    date_col: str = "date"

    # スコアカラム名
    score_col: str = "feature_score"


def _cross_sectional_zscore(df: pd.DataFrame, col: str, group_cols: List[str]) -> pd.Series:
    """
    group_cols（例: [date, size_bucket]）単位で Z-score を計算
    """
    def _z(x: pd.Series) -> pd.Series:
        if x.std(ddof=0) == 0:
            return pd.Series(0.0, index=x.index)
        return (x - x.mean()) / x.std(ddof=0)

    return df.groupby(group_cols)[col].transform(_z)


def assign_size_bucket(
    df: pd.DataFrame,
    config: ScoringEngineConfig,
) -> pd.DataFrame:
    """
    adv_20d のクロスセクションから Large / Mid / Small を機械的に付与。
    ※ 将来的には market_cap ベースに差し替え前提。
    """
    df = df.copy()

    if config.liquidity_col not in df.columns:
        raise KeyError(f"{config.liquidity_col} がありません。columns={df.columns.tolist()}")

    # 日付ごとに 3分位で区切る
    def _bucket_for_day(x: pd.Series) -> pd.Series:
        # NaN は一旦 Mid 扱い
        if x.notna().sum() < 3:
            return pd.Series(["Mid"] * len(x), index=x.index)

        q1 = x.quantile(1 / 3)
        q2 = x.quantile(2 / 3)

        bucket = pd.Series(index=x.index, dtype="object")
        bucket[x >= q2] = "Large"
        bucket[(x >= q1) & (x < q2)] = "Mid"
        bucket[x < q1] = "Small"
        bucket = bucket.fillna("Mid")

        return bucket

    df[config.size_bucket_col] = (
        df.groupby(config.date_col)[config.liquidity_col]
        .transform(_bucket_for_day)
    )

    return df


def build_daily_portfolio(
    df_features: pd.DataFrame,
    config: Optional[ScoringEngineConfig] = None,
) -> pd.DataFrame:
    """
    入力:
        df_features: feature_builder 出力 DataFrame
            必須カラム: date, symbol, feature_score, adv_20d など

    出力:
        daily_portfolio DataFrame:
            date, symbol, size_bucket, feature_score, z_score_bucket, weight, selected
    """
    if config is None:
        config = ScoringEngineConfig()

    required_cols = [
        config.date_col,
        "symbol",
        config.score_col,
        config.liquidity_col,
    ]

    for c in required_cols:
        if c not in df_features.columns:
            raise KeyError(f"必須カラム {c} がありません。columns={df_features.columns.tolist()}")

    df = df_features.copy()

    # 1. size bucket を付与（まだ無ければ）
    if config.size_bucket_col not in df.columns:
        df = assign_size_bucket(df, config)

    # 2. bucket 内 Z-score
    df["z_score_bucket"] = _cross_sectional_zscore(
        df,
        config.score_col,
        [config.date_col, config.size_bucket_col],
    )

    # 3. 日次 & bucket ごとの上位銘柄選定
    #    → まずは target 数を算出
    def _select_for_day(day_df: pd.DataFrame) -> pd.DataFrame:
        day_df = day_df.copy()

        n_total = config.max_names_per_day

        per_bucket_target = {
            bucket: max(int(n_total * w), 1)
            for bucket, w in config.size_bucket_weights.items()
        }

        day_df["selected"] = False

        # 各 bucket ごとに上位を選定
        for bucket, n_target in per_bucket_target.items():
            mask_bucket = day_df[config.size_bucket_col] == bucket
            tmp = day_df[mask_bucket]

            if tmp.empty:
                continue

            # 閾値でフィルタ
            tmp = tmp[tmp[config.score_col] >= config.min_score_threshold]

            if tmp.empty:
                continue

            tmp = tmp.sort_values(config.score_col, ascending=False).head(n_target)

            day_df.loc[tmp.index, "selected"] = True

        # 4. weight 計算
        sel = day_df[day_df["selected"]]

        if sel.empty:
            day_df["weight"] = 0.0
            return day_df

        if config.weighting_scheme == "equal":
            w = 1.0 / len(sel)
            day_df["weight"] = np.where(day_df["selected"], w, 0.0)
        elif config.weighting_scheme == "score":
            scores = sel[config.score_col].clip(lower=0)
            if scores.sum() == 0:
                w = 1.0 / len(sel)
                day_df["weight"] = np.where(day_df["selected"], w, 0.0)
            else:
                w_series = scores / scores.sum()
                day_df["weight"] = 0.0
                day_df.loc[sel.index, "weight"] = w_series
        else:
            raise ValueError(f"未知の weighting_scheme: {config.weighting_scheme}")

        return day_df

    df = df.groupby(config.date_col, group_keys=False).apply(_select_for_day)

    # 出力カラムを整理
    out_cols = [
        config.date_col,
        "symbol",
        config.size_bucket_col,
        config.score_col,
        "z_score_bucket",
        "selected",
        "weight",
    ]

    # 存在するものだけ返す
    out_cols = [c for c in out_cols if c in df.columns]

    return df[out_cols].sort_values([config.date_col, config.size_bucket_col, config.score_col], ascending=[True, True, False])
