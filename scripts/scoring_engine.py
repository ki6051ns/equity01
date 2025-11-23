# scripts/scoring_engine.py
# 3.1 銘柄スコアリング＆ウェイト計算 v0.1

from pathlib import Path
from typing import Dict, List
import sys

import numpy as np
import pandas as pd
import yaml

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_builder import build_features_for_universe


def _load_config(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_universe_tickers(universe_path: Path) -> List[str]:
    df = pd.read_parquet(universe_path)
    if "ticker" not in df.columns:
        raise ValueError("universe parquet must have 'ticker' column.")
    return df["ticker"].unique().tolist()


def compute_scores(asof: str, cfg: Dict) -> pd.DataFrame:
    """
    asof 時点での Score_i, weight_i を計算して返す。

    Returns
    -------
    scores : pd.DataFrame
        index: ticker
        columns: ['score_raw', 'score_penalized',
                  'sigma', 'weight']
    """
    universe_path = PROJECT_ROOT / cfg["universe"]["path"]
    tickers = _load_universe_tickers(universe_path)

    feats = build_features_for_universe(tickers, asof, cfg)

    # 各銘柄の直近行（asof 指定ならその日、それ以外は最後の行）
    df = feats.reset_index()
    if asof != "latest":
        asof_dt = pd.to_datetime(asof)
        df = df[df["date"] <= asof_dt]

    # 各 ticker の最終行を使用
    df = (
        df.sort_values(["ticker", "date"])
          .groupby("ticker")
          .tail(1)
          .set_index("ticker")
    )

    sc_cfg = cfg["scoring"]
    ft_cfg = cfg["features"]

    # ベーススコア
    score_raw = (
        sc_cfg["weight_mom_short"] * df["ret_5_z"] +
        sc_cfg["weight_mom_mid"]   * df["ret_20_z"] +
        sc_cfg["weight_strength"]  * df["strength"]
    )

    # ペナルティ
    penalty = 0.0

    # 過熱ペナルティ
    if "heat_flag" in df.columns:
        penalty = penalty + sc_cfg["penalty_heat"] * df["heat_flag"]

    # 低流動性ペナルティ（ADV 下位 illiq_pct_threshold）
    if "adv_20" in df.columns:
        adv_rank = df["adv_20"].rank(pct=True)
        thr = float(ft_cfg["illiq_pct_threshold"])
        low_liq = (adv_rank < thr).astype(float)
        penalty = penalty + sc_cfg["penalty_illiq"] * low_liq

    score_penalized = score_raw + penalty

    # σ_i（ボラ）
    sigma = df["vol_20"].copy()
    sigma = sigma.fillna(0.0)
    vol_floor = float(ft_cfg["vol_floor"])
    sigma = sigma.clip(lower=vol_floor)

    alpha = float(sc_cfg["alpha"])
    beta = float(sc_cfg["beta"])

    score_pos = score_penalized.clip(lower=0.0)
    raw_w = (score_pos ** alpha) / (sigma ** beta)

    # 全体正規化
    if raw_w.sum() > 0:
        weight = raw_w / raw_w.sum()
    else:
        weight = raw_w.copy()  # 全ゼロ

    # 単一銘柄上限
    max_w = float(cfg["constraints"]["max_weight_single"])
    if max_w > 0:
        weight = weight.clip(upper=max_w)
        if weight.sum() > 0:
            weight = weight / weight.sum()

    out = pd.DataFrame({
        "score_raw": score_raw,
        "score_penalized": score_penalized,
        "sigma": sigma,
        "weight": weight,
    })

    # スコア順に並べる
    out = out.sort_values("score_penalized", ascending=False)

    return out


def run_from_config(config_path: Path) -> pd.DataFrame:
    cfg = _load_config(config_path)
    asof = cfg.get("asof", "latest")
    scores = compute_scores(asof, cfg)

    # 保存
    out_dir = PROJECT_ROOT / cfg["output"]["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    asof_str = asof
    if asof_str == "latest":
        # 実際の asof 日付は scores.index から拾うほど厳密でなくてOK。
        asof_str = "latest"

    pattern = cfg["output"].get("filename_pattern", "{asof}_scores.parquet")
    fname = pattern.format(asof=asof_str)
    out_path = out_dir / fname
    scores.to_parquet(out_path)

    return scores
