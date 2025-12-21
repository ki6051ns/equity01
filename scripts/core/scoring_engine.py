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
from pathlib import Path
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
            "Large": 0.4,
            "Mid": 0.4,
            "Small": 0.2,
        }
    )

    # bucket 内で銘柄を選ぶ際の最小スコア閾値（後方互換性のため残す）
    min_score_threshold: float = -np.inf  # とりあえず制約なし

    # 最終的に weight をどう計算するか
    # "equal": 同一重み, "score": feature_score 比例, "zscore": z_score_bucket 比例
    weighting_scheme: Literal["equal", "score", "zscore"] = "zscore"
    
    # バケット内 z-score の最小閾値（弱いスコアを切る）
    min_zscore: float = 0.0  # 0.0 以上なら弱い銘柄を除外

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
    def _select_for_day(day_df: pd.DataFrame) -> pd.DataFrame:
        day_df = day_df.copy()

        n_total = config.max_names_per_day

        per_bucket_target = {
            bucket: max(int(n_total * w), 1)
            for bucket, w in config.size_bucket_weights.items()
        }

        # --- バケットごとの Z-score 再計算 -----------------------------
        def z_in_bucket(g: pd.DataFrame) -> pd.DataFrame:
            x = g[config.score_col].astype(float)
            mu = x.mean()
            sigma = x.std(ddof=0)
            if sigma == 0:
                g["z_score_bucket"] = 0.0
            else:
                g["z_score_bucket"] = (x - mu) / sigma
            return g

        day_df = day_df.groupby(config.size_bucket_col, group_keys=False).apply(z_in_bucket)

        # 閾値で「弱いスコア」を切る（動きを出すポイント）
        min_z = config.min_zscore
        day_df = day_df[day_df["z_score_bucket"] > min_z].copy()

        # 初期化
        day_df["selected"] = False
        day_df["weight"] = 0.0

        # --- 各 bucket ごとに銘柄を選定＆ウェイト付け -------------------
        for bucket, n_target in per_bucket_target.items():
            bucket_df = day_df[day_df[config.size_bucket_col] == bucket]

            if bucket_df.empty:
                continue

            # z_score 高い順に並べて上位 n_target を取る
            bucket_df = bucket_df.sort_values("z_score_bucket", ascending=False)
            selected = bucket_df.head(n_target)

            idx = selected.index

            if config.weighting_scheme == "equal":
                w = 1.0 / len(selected)
                day_df.loc[idx, "weight"] = w

            elif config.weighting_scheme == "zscore":
                # 正の z-score を重みとして正規化
                z = selected["z_score_bucket"].clip(lower=0.0)
                total = z.sum()
                if total > 0:
                    day_df.loc[idx, "weight"] = z / total
                else:
                    # すべて同じ or 0 なら等ウェイト fallback
                    w = 1.0 / len(selected)
                    day_df.loc[idx, "weight"] = w

            elif config.weighting_scheme == "score":
                s = selected[config.score_col].clip(lower=0.0)
                total = s.sum()
                if total > 0:
                    day_df.loc[idx, "weight"] = s / total
                else:
                    w = 1.0 / len(selected)
                    day_df.loc[idx, "weight"] = w

            else:
                raise ValueError(f"未知の weighting_scheme: {config.weighting_scheme}")

            # 選定フラグ
            day_df.loc[idx, "selected"] = True

        # --- 日次のウェイトを全体で再正規化（保険的に） -----------------
        w_sum = day_df["weight"].sum()
        if w_sum > 0:
            day_df["weight"] = day_df["weight"] / w_sum

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


def compute_scores_all(
    df: pd.DataFrame,
    base_col: str,
    group_cols: tuple = ("date",),
    ascending: bool = False,
) -> pd.DataFrame:
    """
    スコアリングの複数方式を一括計算
    
    入力:
        df: 入力DataFrame（base_colを含む）
        base_col: スコア計算の元となるカラム名
        group_cols: グループ化カラム（例: ("date",) または ("date", "sector")）
        ascending: ランキングの順序（False=大きいほど上位）
    
    出力:
        dfに以下を追加:
        - score_z_lin: Z-score線形結合（base_colのZ-score）
        - score_rank_only: ランクベーススコア（0-1正規化）
    """
    df = df.copy()
    
    if base_col not in df.columns:
        raise KeyError(f"base_col '{base_col}' が見つかりません")
    
    # Z-score計算（group_cols単位）
    def _zscore(x: pd.Series) -> pd.Series:
        if x.std(ddof=0) == 0:
            return pd.Series(0.0, index=x.index)
        return (x - x.mean()) / x.std(ddof=0)
    
    df["score_z_lin"] = df.groupby(list(group_cols))[base_col].transform(_zscore)
    
    # ランクベーススコア（0-1正規化）
    def _rank_score(x: pd.Series) -> pd.Series:
        if len(x) == 0:
            return pd.Series(0.0, index=x.index)
        ranks = x.rank(ascending=ascending, method="min")
        return (ranks - 1) / (len(x) - 1) if len(x) > 1 else pd.Series(0.0, index=x.index)
    
    df["score_rank_only"] = df.groupby(list(group_cols))[base_col].transform(_rank_score)
    
    return df


def _zscore(x: pd.Series) -> pd.Series:
    """
    Z-score計算ヘルパー関数
    
    この関数は build_features.py から使用されます。
    """
    if x.std(ddof=0) == 0:
        return pd.Series(0.0, index=x.index)
    return (x - x.mean()) / x.std(ddof=0)


def run_from_config(config_path: Path) -> pd.DataFrame:
    """
    設定ファイルからスコアを計算
    
    入力:
        config_path: YAML設定ファイルのパス
    
    出力:
        スコアDataFrame
    """
    import yaml
    from pathlib import Path as PathLib
    
    # 設定ファイル読み込み
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    # 簡易実装: 設定ファイルから必要な情報を読み込んでスコア計算
    # 実際の実装は設定ファイルの内容に依存します
    # ここでは最小限の実装を提供
    
    # 入力ファイルパス（設定ファイルから取得）
    input_path = PathLib(cfg.get("input", {}).get("features", "data/processed/daily_feature_scores.parquet"))
    
    if not input_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")
    
    df = pd.read_parquet(input_path)
    
    # スコア計算（設定ファイルのパラメータに基づく）
    base_col = cfg.get("scoring", {}).get("base_col", "feature_raw")
    group_cols = tuple(cfg.get("scoring", {}).get("group_cols", ["date"]))
    
    if base_col not in df.columns:
        # fallback: feature_scoreがあればそれを使う
        if "feature_score" in df.columns:
            base_col = "feature_score"
        else:
            raise KeyError(f"base_col '{base_col}' が見つかりません。利用可能なカラム: {df.columns.tolist()}")
    
    df = compute_scores_all(df, base_col=base_col, group_cols=group_cols)
    
    # 出力パス（設定ファイルから取得）
    output_path = PathLib(cfg.get("output", {}).get("path", "data/intermediate/scoring/latest_scores.parquet"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    
    return df