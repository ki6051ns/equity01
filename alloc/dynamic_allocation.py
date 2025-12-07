#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
alloc/dynamic_allocation.py

動的ウェイト計算モジュール

rank_only/cross3/最小分散/インバースなど、複数スリーブの動的配分を行う。
リスクパリティの考え方に基づいて、各スリーブのリスクに応じてウェイトを調整。
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional


def compute_dynamic_weights(
    returns: pd.DataFrame,
    window: int = 252,
    priors: Optional[Dict[str, float]] = None,
    bounds: Optional[Dict[str, Tuple[float, float]]] = None,
    method: str = "sqrt_sigma",
    eps: float = 1e-8,
) -> pd.DataFrame:
    """
    動的ウェイト計算（rank_only/cross3/最小分散/インバースなど共通モジュール）

    Parameters
    ----------
    returns : DataFrame
        各スリーブの日次リターン.
        列名は "rank_only", "cross3", "minvar", "inverse" など。
    window : int, default 252
        ローリング期間（日数）.
    priors : dict, optional
        {col_name: prior_weight} の辞書.
        None の場合は等ウェイトを使用.
    bounds : dict, optional
        {col_name: (min_weight, max_weight)} の辞書.
        None の場合はクリップしない.
    method : {"sqrt_sigma", "sigma"}, default "sqrt_sigma"
        リスクパリティの分母.
        - "sqrt_sigma":  1 / sqrt(σ)（提案の基本形）
        - "sigma":       1 / σ
    eps : float, default 1e-8
        0除算回避用の小さい値.

    Returns
    -------
    weights : DataFrame
        各スリーブの日次ウェイト（行：日付, 列：スリーブ）.
        早期の window 未満期間は前方埋め / 後方埋めで補完済み.
    """
    cols = list(returns.columns)

    # priors: 未指定なら等ウェイト
    if priors is None:
        priors = {c: 1.0 / len(cols) for c in cols}
    else:
        # 指定されていない列があれば等ウェイトで埋める
        missing = [c for c in cols if c not in priors]
        if missing:
            equal = (1.0 - sum(priors.get(c, 0.0) for c in cols)) / max(len(missing), 1)
            for c in missing:
                priors[c] = equal

    # ローリングσ
    sigma = returns.rolling(window).std()

    # 分母の形を選択
    if method == "sqrt_sigma":
        denom = np.sqrt(sigma + eps)
    elif method == "sigma":
        denom = sigma + eps
    else:
        raise ValueError(f"Unknown method: {method}")

    # raw weight = prior / denom
    raw = pd.DataFrame(index=returns.index, columns=cols, dtype=float)
    for c in cols:
        raw[c] = priors.get(c, 0.0) / denom[c]

    # 行方向で正規化
    weights = raw.div(raw.sum(axis=1), axis=0)

    # bounds でクリップ
    if bounds is not None:
        for c in cols:
            if c in bounds:
                lo, hi = bounds[c]
                weights[c] = weights[c].clip(lo, hi)

        # 再度 正規化（合計=1）
        weights = weights.div(weights.sum(axis=1), axis=0)

    # window 以前の NaN を補完（最初の有効値で埋める）
    first_valid_idx = weights.dropna(how="all").index
    if len(first_valid_idx) > 0:
        first_valid = first_valid_idx.min()
        # 前方補完
        weights.loc[first_valid:] = weights.loc[first_valid:].ffill()
        # 最初の有効値より前は、最初の有効値で埋める
        if weights.index.min() < first_valid:
            first_valid_row = weights.loc[first_valid].copy()
            for idx in weights.index[weights.index < first_valid]:
                weights.loc[idx] = first_valid_row.values

    return weights

