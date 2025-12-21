from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Iterable, Literal

import pandas as pd


ScoreType = Literal[
    "zscore_linear",
    "rank_linear",
    "zscore_with_rank_tilt",
    "zscore_lowvol",
    "zscore_downvol",
    "zscore_downbeta",
    "zscore_downcombo",
]


@dataclass
class ScoringVariantConfig:
    type: ScoreType
    clip: Tuple[float, float] | None = None
    inverse: bool = False  # rank の場合にリバーサルするかどうか
    # Variant C 用パラメータ
    top_n: int | None = None
    bottom_n: int | None = None
    tilt_strength: float | None = None
    # Variant D 用パラメータ
    lambda_vol: float | None = None
    lambda_beta: float | None = None
    vol_col: str | None = None
    beta_col: str | None = None
    # Variant E/F/G 用パラメータ
    lambda_vol_down: float | None = None
    lambda_beta_down: float | None = None
    vol_down_col: str | None = None
    beta_down_col: str | None = None


SCORING_VARIANTS: Dict[str, ScoringVariantConfig | dict] = {
    # Variant A: 基準（現行）z-score 線形
    "z_lin": ScoringVariantConfig(
        type="zscore_linear",
        clip=(-3.0, 3.0),
    ),
    # Variant B: 純 rank ベース
    "rank_only": ScoringVariantConfig(
        type="rank_linear",
        clip=None,       # rank は [-1,+1]に正規化するのでクリップ不要
        inverse=False,   # リバーサルなら True にする
    ),
    # Variant C: z-score + rank tilt
    "z_clip_rank": {
        "type": "zscore_with_rank_tilt",
        "clip": (-2.0, 2.0),
        "top_n": 10,
        "bottom_n": 10,
        "tilt_strength": 0.3,
    },
    # Variant D: z-score - low vol/beta penalty
    "z_lowvol": {
        "type": "zscore_lowvol",
        "clip": (-3.0, 3.0),
        "lambda_vol": 0.5,
        "lambda_beta": 0.3,
        "vol_col": "vol_20d_z",
        "beta_col": "beta_252d_z",
    },
    # Variant E: z-score - downside vol penalty
    "z_downvol": {
        "type": "zscore_downvol",
        "clip": (-3.0, 3.0),
        "lambda_vol_down": 0.7,
        "vol_down_col": "downside_vol_60d",
    },
    # Variant F: z-score - downside beta penalty
    "z_downbeta": {
        "type": "zscore_downbeta",
        "clip": (-3.0, 3.0),
        "lambda_beta_down": 0.5,
        "beta_down_col": "down_beta_252d",
    },
    # Variant G: z-score - downside vol + beta combo
    "z_downcombo": {
        "type": "zscore_downcombo",
        "clip": (-3.0, 3.0),
        "lambda_vol_down": 0.5,
        "lambda_beta_down": 0.3,
        "vol_down_col": "downside_vol_60d",
        "beta_down_col": "down_beta_252d",
    },
}


def _zscore(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / (x.std(ddof=1) + 1e-8)


def _rank_scaled(x: pd.Series) -> pd.Series:
    """
    0〜1 のランクを -1〜+1 にスケール。
    ascending=False にする側で呼べば「上位ほど +1」にできる。
    """
    r = x.rank(method="first")  # 1,2,3,...
    return 2.0 * (r - r.min()) / (r.max() - r.min() + 1e-8) - 1.0


def compute_scores_all(
    df: pd.DataFrame,
    base_col: str,
    *,
    group_cols: Iterable[str] = ("date",),
    ascending: bool = True,
) -> pd.DataFrame:
    """
    各 SCORING_VARIANTS ごとに score_<name> カラムを追加する。

    Parameters
    ----------
    df : features DataFrame
    base_col : factor の元カラム（例: "raw_mom_score"）
    group_cols : 日次 or 日次×セクターなど
    ascending : True なら「値が小さいほど rank 1」、False なら「大きいほど rank 1」
    """
    g = df.groupby(list(group_cols))

    for name, cfg in SCORING_VARIANTS.items():
        out_col = f"score_{name}"
        
        # 辞書形式の場合はそのまま使用、dataclass の場合は辞書に変換
        if isinstance(cfg, dict):
            cfg_dict = cfg
            cfg_type = cfg_dict["type"]
        else:
            cfg_dict = {
                "type": cfg.type,
                "clip": cfg.clip,
                "inverse": cfg.inverse,
                "top_n": cfg.top_n,
                "bottom_n": cfg.bottom_n,
                "tilt_strength": cfg.tilt_strength,
                "lambda_vol": cfg.lambda_vol,
                "lambda_beta": cfg.lambda_beta,
                "vol_col": cfg.vol_col,
                "beta_col": cfg.beta_col,
                "lambda_vol_down": cfg.lambda_vol_down,
                "lambda_beta_down": cfg.lambda_beta_down,
                "vol_down_col": cfg.vol_down_col,
                "beta_down_col": cfg.beta_down_col,
            }
            cfg_type = cfg.type

        if cfg_type == "zscore_linear":
            s = g[base_col].transform(_zscore)
            if cfg_dict.get("clip") is not None:
                lo, hi = cfg_dict["clip"]
                s = s.clip(lo, hi)
            df[out_col] = s

        elif cfg_type == "rank_linear":
            # base_col の値で昇順/降順を切り替え
            def _rank_group(x: pd.Series) -> pd.Series:
                r = x.rank(method="first", ascending=ascending)
                return _rank_scaled(r)

            s = g[base_col].transform(_rank_group)
            if cfg_dict.get("inverse", False):
                s = -s
            df[out_col] = s

        elif cfg_type == "zscore_with_rank_tilt":
            # Variant C: z-score + rank tilt
            s_z = g[base_col].transform(_zscore)
            lo, hi = cfg_dict["clip"]
            s_z = s_z.clip(lo, hi)

            # rank tilt
            def _tilt_block(x: pd.Series) -> pd.Series:
                r = x.rank(method="first", ascending=False)
                n = len(x)
                top_n = cfg_dict["top_n"]
                bottom_n = cfg_dict["bottom_n"]
                alpha = cfg_dict["tilt_strength"]
                
                w = pd.Series(0.0, index=x.index)
                w[r <= top_n] = +alpha
                w[r > n - bottom_n] = -alpha
                return w

            tilt = g[base_col].transform(_tilt_block)
            df[out_col] = (s_z + tilt).clip(-3, 3)

        elif cfg_type == "zscore_lowvol":
            # Variant D: z-score - low vol/beta penalty
            s_z = g[base_col].transform(_zscore)
            lo, hi = cfg_dict["clip"]
            s_z = s_z.clip(lo, hi)

            lv = cfg_dict.get("lambda_vol", 0.0)
            lb = cfg_dict.get("lambda_beta", 0.0)

            vol_col = cfg_dict.get("vol_col")
            beta_col = cfg_dict.get("beta_col")

            # vol_z の取得（なければ 0 扱い）
            if vol_col is not None and vol_col in df.columns:
                vol_z = df[vol_col]
            elif "vol_20d" in df.columns:
                # on-the-fly で z-score を作る簡易版
                vol_z = g["vol_20d"].transform(_zscore)
            else:
                vol_z = pd.Series(0.0, index=df.index)

            # beta_z の取得（なければ 0 扱い）
            if beta_col is not None and beta_col in df.columns:
                beta_z = df[beta_col]
            else:
                beta_z = pd.Series(0.0, index=df.index)

            df[out_col] = (s_z - lv * vol_z - lb * beta_z).clip(-3, 3)

        elif cfg_type == "zscore_downvol":
            # Variant E: z-score - downside vol penalty
            s_z = g[base_col].transform(_zscore)
            lo, hi = cfg_dict["clip"]
            s_z = s_z.clip(lo, hi)

            lambda_vol_down = cfg_dict.get("lambda_vol_down", 0.7)
            vol_down_col = cfg_dict.get("vol_down_col", "downside_vol_60d")

            # vol_down_z の取得（なければ 0 扱い）
            if vol_down_col is not None and vol_down_col in df.columns:
                vol_down_z = g[vol_down_col].transform(_zscore)
            else:
                vol_down_z = pd.Series(0.0, index=df.index)

            df[out_col] = (s_z - lambda_vol_down * vol_down_z).clip(-3, 3)

        elif cfg_type == "zscore_downbeta":
            # Variant F: z-score - downside beta penalty
            s_z = g[base_col].transform(_zscore)
            lo, hi = cfg_dict["clip"]
            s_z = s_z.clip(lo, hi)

            lambda_beta_down = cfg_dict.get("lambda_beta_down", 0.5)
            beta_down_col = cfg_dict.get("beta_down_col", "down_beta_252d")

            # beta_down_z の取得（なければ 0 扱い）
            if beta_down_col is not None and beta_down_col in df.columns:
                beta_down_z = g[beta_down_col].transform(_zscore)
            else:
                beta_down_z = pd.Series(0.0, index=df.index)

            df[out_col] = (s_z - lambda_beta_down * beta_down_z).clip(-3, 3)

        elif cfg_type == "zscore_downcombo":
            # Variant G: z-score - downside vol + beta combo
            s_z = g[base_col].transform(_zscore)
            lo, hi = cfg_dict["clip"]
            s_z = s_z.clip(lo, hi)

            lambda_vol_down = cfg_dict.get("lambda_vol_down", 0.5)
            lambda_beta_down = cfg_dict.get("lambda_beta_down", 0.3)
            vol_down_col = cfg_dict.get("vol_down_col", "downside_vol_60d")
            beta_down_col = cfg_dict.get("beta_down_col", "down_beta_252d")

            # vol_down_z の取得（なければ 0 扱い）
            if vol_down_col is not None and vol_down_col in df.columns:
                vol_down_z = g[vol_down_col].transform(_zscore)
            else:
                vol_down_z = pd.Series(0.0, index=df.index)

            # beta_down_z の取得（なければ 0 扱い）
            if beta_down_col is not None and beta_down_col in df.columns:
                beta_down_z = g[beta_down_col].transform(_zscore)
            else:
                beta_down_z = pd.Series(0.0, index=df.index)

            df[out_col] = (s_z - lambda_vol_down * vol_down_z - lambda_beta_down * beta_down_z).clip(-3, 3)

        else:
            raise ValueError(f"Unknown scoring type: {cfg_type}")

    return df
