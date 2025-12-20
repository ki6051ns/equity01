"""
weights_cleaning.py

実務クリーニングレイヤー：
ターゲットウェイトベクトルに対して
- 最小ウェイト閾値カット
- ロング／ショートそれぞれ銘柄数上限
- ロット（100株）単位への丸め＋再スケール
を行う。
"""
from typing import Tuple

import numpy as np
import pandas as pd


def clean_target_weights(
    w: pd.Series,
    prices: pd.Series,
    nav: float = 1.0,
    min_abs_weight: float = 0.003,     # 0.3% 未満はゼロ
    max_names_per_side: int = 30,      # ロング/ショート 各30銘柄まで
    lot_size: int = 100,               # 日本株のロット
    use_lot_rounding: bool = True,
) -> Tuple[pd.Series, pd.Series]:
    """
    ターゲットウェイトベクトル w を「実務的に扱いやすい形」にクリーニングする。

    Args:
        w: ターゲットウェイト（symbolをインデックスとするSeries）
        prices: 当日の終値（symbolをインデックスとするSeries）
        nav: ネットアセットバリュー（デフォルト1.0）
        min_abs_weight: 最小絶対ウェイト閾値（これ未満はゼロ）
        max_names_per_side: ロング/ショートそれぞれの最大銘柄数
        lot_size: ロットサイズ（日本株は100株）
        use_lot_rounding: ロット単位への丸めを行うか

    Returns:
        clean_w: クリーニング後のウェイト（ロングとショートが元の合計に近くなるよう再スケール済み）
        shares: 100株ロットに丸めた株数（use_lot_rounding=False の場合は float でもよい）
    """
    w = w.copy()
    prices = prices.copy()

    # ① 閾値カット（絶対値が小さい銘柄はゼロ）
    mask_keep = w.abs() >= min_abs_weight
    w[~mask_keep] = 0.0

    # フォールバック: 閾値カットで全部消えてしまった場合
    if w.abs().sum() < 1e-8:
        # 絶対値上位 top_k を採用（ロング/ショートそれぞれ）
        top_k = max(5, max_names_per_side // 2)  # 最低5銘柄、最大max_names_per_side/2
        w_original = w.copy()
        w = pd.Series(0.0, index=w.index)
        
        # ロング側
        long_original = w_original[w_original > 0].sort_values(ascending=False)
        if len(long_original) > 0:
            long_top = long_original.head(min(top_k, len(long_original)))
            w.loc[long_top.index] = long_top
        
        # ショート側
        short_original = w_original[w_original < 0].sort_values(ascending=True)
        if len(short_original) > 0:
            short_top = short_original.head(min(top_k, len(short_original)))
            w.loc[short_top.index] = short_top

    # ② ロング/ショートそれぞれで銘柄数を上位 max_names_per_side に制限
    long = w[w > 0].sort_values(ascending=False)
    short = w[w < 0].sort_values(ascending=True)

    if len(long) > max_names_per_side:
        drop_idx = long.index[max_names_per_side:]
        w.loc[drop_idx] = 0.0
    if len(short) > max_names_per_side:
        drop_idx = short.index[max_names_per_side:]
        w.loc[drop_idx] = 0.0

    # ③ ロング・ショートそれぞれで合計ウェイトを再スケール
    long_sum = w[w > 0].sum()
    short_sum = w[w < 0].sum()  # 負値

    if long_sum > 0:
        w[w > 0] = w[w > 0] / long_sum
    if short_sum < 0:
        w[w < 0] = w[w < 0] / abs(short_sum) * (-1.0)

    # ④ 株数に変換（100株ロットへ丸め）
    # nav=1.0 であれば notionals = weights でもよいが、形式上 nav を使う
    # prices: 当日の終値など
    notionals = w * nav
    # 0除算防止
    prices = prices.replace(0, np.nan)

    # 価格がNaNの銘柄は除外
    valid_mask = prices.notna() & (prices > 0)
    raw_shares = pd.Series(index=w.index, dtype=float)
    raw_shares[valid_mask] = notionals[valid_mask] / prices[valid_mask]
    raw_shares[~valid_mask] = 0.0

    if use_lot_rounding:
        # 100株単位に丸める
        lot_units = raw_shares / lot_size
        lot_units = lot_units.round()  # 最近傍
        shares = lot_units * lot_size
    else:
        shares = raw_shares

    # ⑤ ロング/ショートそれぞれで再スケール（ロット丸めによるズレ補正）
    # 実務上は "ロング側の総額/ショート側の総額が大きくズレない" 程度に調整できればよい
    notional_after = shares * prices
    long_notional = notional_after[shares > 0].sum()
    short_notional = notional_after[shares < 0].sum()  # 負値

    # ここでは簡易に「ロングとショートのabs総額を揃える」方向でスケーリング
    if long_notional > 0 and short_notional < 0:
        scale = min(long_notional, abs(short_notional)) / max(long_notional, abs(short_notional))
        # 大きい方を縮小
        if long_notional > abs(short_notional):
            shares[shares > 0] *= scale
        else:
            shares[shares < 0] *= scale

    # final weights を再計算（バックテストではこの clean_w を使えばよい）
    notional_final = shares * prices
    total_abs = (notional_final.abs()).sum()
    if total_abs > 0:
        clean_w = notional_final / total_abs
    else:
        # 最悪ケース: ロット丸めで全部消えた場合は、元のwを正規化して返す
        w_abs_sum = w.abs().sum()
        if w_abs_sum > 0:
            clean_w = w / w_abs_sum
        else:
            clean_w = w * 0.0

    return clean_w, shares

