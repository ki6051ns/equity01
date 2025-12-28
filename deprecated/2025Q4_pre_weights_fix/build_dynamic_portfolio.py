#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/build_dynamic_portfolio.py

rank_only、cross3 の2スリーブを使い、
・√σ（分母）方式
の動的ウェイトポートフォリオを構築
"""

import sys
from pathlib import Path
from typing import Dict, Tuple

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np


def load_sleeve_returns() -> pd.DataFrame:
    """
    各スリーブの日次リターンを読み込む（rank_only と cross3 の2スリーブ）
    
    Returns
    -------
    pd.DataFrame
        各スリーブの日次リターン（列: rank_only, cross3）
        日付で inner join して揃える
    """
    data_dir = Path("data/processed")
    
    sleeves = {}
    
    # rank_only: horizon_ensemble_rank_only.parquet から port_ret_cc_ens を使用
    try:
        df_rank = pd.read_parquet(data_dir / "horizon_ensemble_rank_only.parquet")
        date_col = "trade_date" if "trade_date" in df_rank.columns else "date"
        if "port_ret_cc_ens" in df_rank.columns:
            sleeves["rank_only"] = df_rank.set_index(date_col)["port_ret_cc_ens"]
        else:
            port_cols = [c for c in df_rank.columns if "port_ret_cc" in c]
            if port_cols:
                sleeves["rank_only"] = df_rank.set_index(date_col)[port_cols[0]]
            else:
                raise ValueError("port_ret_cc column not found in rank_only data")
        print(f"[INFO] Loaded rank_only: {len(sleeves['rank_only'])} days")
    except Exception as e:
        raise FileNotFoundError(f"Failed to load rank_only: {e}")
    
    # cross3: horizon_ensemble_variant_cross3.parquet から port_ret_cc_ens を使用
    try:
        df_cross3 = pd.read_parquet(data_dir / "horizon_ensemble_variant_cross3.parquet")
        date_col = "trade_date" if "trade_date" in df_cross3.columns else "date"
        if "port_ret_cc_ens" in df_cross3.columns:
            sleeves["cross3"] = df_cross3.set_index(date_col)["port_ret_cc_ens"]
        else:
            port_cols = [c for c in df_cross3.columns if "port_ret_cc" in c]
            if port_cols:
                sleeves["cross3"] = df_cross3.set_index(date_col)[port_cols[0]]
            else:
                raise ValueError("port_ret_cc column not found in cross3 data")
        print(f"[INFO] Loaded cross3: {len(sleeves['cross3'])} days")
    except Exception as e:
        raise FileNotFoundError(f"Failed to load cross3: {e}")
    
    # 全てのスリーブをDataFrameにまとめ、日付で inner join
    returns_df = pd.DataFrame(sleeves)
    
    # NaNを削除（全スリーブが揃っている期間のみ）
    returns_df = returns_df.dropna()
    
    print(f"\n[INFO] Combined returns DataFrame:")
    print(f"  Shape: {returns_df.shape}")
    print(f"  Date range: {returns_df.index.min()} ～ {returns_df.index.max()}")
    print(f"  Columns: {list(returns_df.columns)}")
    
    return returns_df


def compute_volatilities(returns_df: pd.DataFrame, window: int = 252) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    252日ローリングでボラティリティを計算
    
    Parameters
    ----------
    returns_df : pd.DataFrame
        各スリーブの日次リターン
    window : int
        ローリング期間（デフォルト: 252日）
    
    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        (sigma, root_sigma) のタプル
        - sigma: 252日ローリング標準偏差
        - root_sigma: sqrt(標準偏差)
        NaNは直前値で forward-fill
    """
    # ローリング標準偏差
    sigma = returns_df.rolling(window=window, min_periods=1).std()
    
    # sqrt(sigma)
    root_sigma = np.sqrt(sigma)
    
    # NaNを直前値で forward-fill
    sigma = sigma.ffill()
    root_sigma = root_sigma.ffill()
    
    # 最初のNaNは後方埋め
    sigma = sigma.bfill()
    root_sigma = root_sigma.bfill()
    
    return sigma, root_sigma


def compute_weights(
    priors: Dict[str, float],
    vols: Dict[str, float],
    bounds: Dict[str, Tuple[float, float]],
    mode: str,
    eps: float = 1e-8,
) -> Dict[str, float]:
    """
    ウェイトを計算（共通モジュール）
    
    Parameters
    ----------
    priors : dict
        事前ウェイト（例: {"rank_only": 0.45, "cross3": 0.25, ...}）
    vols : dict
        各スリーブのボラティリティ（sigma または root_sigma）
    bounds : dict
        スリーブごとの最小・最大ウェイト（例: {"rank_only": (0.30, 0.60), ...}）
    mode : str
        "sigma" または "sqrt_sigma"
    eps : float
        0除算回避用の小さい値
    
    Returns
    -------
    dict
        各スリーブのウェイト（合計=1.0）
    
    目的関数:
        w_i = prior_i / vol_i
        normalize(w)
        bounds を守るようにクリッピング
        最後に再正規化
    """
    # 1. raw weight = prior / vol
    raw_weights = {}
    for sleeve in priors.keys():
        if sleeve not in vols:
            raise ValueError(f"Volatility not found for sleeve: {sleeve}")
        vol = vols[sleeve]
        if vol < eps:
            vol = eps
        raw_weights[sleeve] = priors[sleeve] / vol
    
    # 2. 正規化
    total = sum(raw_weights.values())
    if total == 0:
        # 等ウェイトにフォールバック
        raw_weights = {sleeve: 1.0 / len(priors) for sleeve in priors.keys()}
    else:
        raw_weights = {sleeve: w / total for sleeve, w in raw_weights.items()}
    
    # 3. bounds でクリッピング
    clipped_weights = {}
    for sleeve in priors.keys():
        if sleeve in bounds:
            lo, hi = bounds[sleeve]
            clipped_weights[sleeve] = max(lo, min(hi, raw_weights[sleeve]))
        else:
            clipped_weights[sleeve] = raw_weights[sleeve]
    
    # 4. 再正規化（合計=1.0）
    total = sum(clipped_weights.values())
    if total == 0:
        # 等ウェイトにフォールバック
        final_weights = {sleeve: 1.0 / len(priors) for sleeve in priors.keys()}
    else:
        final_weights = {sleeve: w / total for sleeve, w in clipped_weights.items()}
    
    # 5. 最終的にboundsを再確認（正規化後にboundsを超える場合があるため）
    # ただし、この場合は最小限の調整のみ行う
    for sleeve in final_weights.keys():
        if sleeve in bounds:
            lo, hi = bounds[sleeve]
            if final_weights[sleeve] < lo:
                final_weights[sleeve] = lo
            elif final_weights[sleeve] > hi:
                final_weights[sleeve] = hi
    
    # 再度正規化（bounds調整後）
    total = sum(final_weights.values())
    if total > 0:
        final_weights = {sleeve: w / total for sleeve, w in final_weights.items()}
    else:
        # 等ウェイトにフォールバック
        final_weights = {sleeve: 1.0 / len(priors) for sleeve in priors.keys()}
    
    return final_weights


def build_dynamic_portfolio(
    returns_df: pd.DataFrame,
    window: int = 252,
    priors: Dict[str, float] = None,
    bounds: Dict[str, Tuple[float, float]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    動的ウェイトポートフォリオを構築（√σ方式のみ）
    
    Parameters
    ----------
    returns_df : pd.DataFrame
        各スリーブの日次リターン
    window : int
        ローリング期間（デフォルト: 252日）
    priors : dict
        事前ウェイト
    bounds : dict
        ウェイトの上下限
    
    Returns
    -------
    dict
        weights_sqrt, combined_ret_sqrt, combined_index_sqrt を含む
    """
    # 事前ウェイトの設定
    if priors is None:
        priors = {
            "rank_only": 0.50,
            "cross3": 0.50,
        }
    
    # ウェイトの上下限
    if bounds is None:
        bounds = {
            "rank_only": (0.30, 0.70),
            "cross3": (0.30, 0.70),
        }
    
    print(f"\n[INFO] Computing dynamic weights with window={window}")
    print(f"  Priors: {priors}")
    print(f"  Bounds: {bounds}")
    
    # ボラティリティを計算
    print("\n[INFO] Computing volatilities...")
    sigma, root_sigma = compute_volatilities(returns_df, window=window)
    
    # 日次ウェイトを計算（√σ方式のみ）
    print("[INFO] Computing daily weights (sqrt_sigma method)...")
    weights_sqrt_list = []
    
    for date in returns_df.index:
        # その日のボラティリティ（√σ方式）
        root_sigma_t = {sleeve: float(root_sigma.loc[date, sleeve]) for sleeve in returns_df.columns}
        
        # √σ方式
        w_sqrt = compute_weights(priors, root_sigma_t, bounds, mode="sqrt_sigma")
        weights_sqrt_list.append({**{"date": date}, **w_sqrt})
    
    # DataFrameに変換
    weights_sqrt = pd.DataFrame(weights_sqrt_list).set_index("date")
    
    # 列の順序を揃える
    weights_sqrt = weights_sqrt[returns_df.columns]
    
    # 合成リターンを計算
    print("[INFO] Computing combined returns...")
    combined_ret_sqrt = (returns_df * weights_sqrt).sum(axis=1)
    combined_index_sqrt = (1 + combined_ret_sqrt).cumprod()
    
    # 検証: ウェイト合計が常に1.0であることを確認
    assert np.allclose(weights_sqrt.sum(axis=1), 1.0), "weights_sqrt合計が1.0ではありません"
    
    print("[INFO] Validation passed: All weights sum to 1.0")
    
    return {
        "weights_sqrt": weights_sqrt,
        "combined_ret_sqrt": combined_ret_sqrt,
        "combined_index_sqrt": combined_index_sqrt,
    }


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== 動的ウェイト配分ポートフォリオ構築 ===")
    print("=" * 80)
    
    # 1. 各スリーブのリターンを読み込む
    print("\n[STEP 1] Loading sleeve returns...")
    returns_df = load_sleeve_returns()
    
    if returns_df is None or returns_df.empty:
        print("[ERROR] Failed to load returns data")
        return
    
    # 2. 動的ウェイト配分ポートフォリオを構築
    print("\n[STEP 2] Building dynamic portfolio...")
    
    priors = {
        "rank_only": 0.50,
        "cross3": 0.50,
    }
    
    bounds = {
        "rank_only": (0.30, 0.70),
        "cross3": (0.30, 0.70),
    }
    
    results = build_dynamic_portfolio(
        returns_df=returns_df,
        window=252,
        priors=priors,
        bounds=bounds,
    )
    
    # 3. 結果を保存
    print("\n[STEP 3] Saving results...")
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # √σパリティ版
    out_sqrt = pd.DataFrame({
        "trade_date": returns_df.index,
        "date": returns_df.index,  # 互換性のため両方保存
        "combined_ret_sqrt": results["combined_ret_sqrt"],
        "combined_index_sqrt": results["combined_index_sqrt"],
    })
    out_sqrt_path = output_dir / "portfolio_root_sigma.parquet"
    out_sqrt.to_parquet(out_sqrt_path, index=False)
    print(f"[INFO] Saved sqrt_sigma portfolio to {out_sqrt_path}")
    
    # ウェイトも保存
    weights_sqrt_df = results["weights_sqrt"].reset_index()
    weights_sqrt_df = weights_sqrt_df.rename(columns={"index": "date"})
    weights_sqrt_path = output_dir / "dynamic_weights_root_sigma.parquet"
    weights_sqrt_df.to_parquet(weights_sqrt_path, index=False)
    print(f"[INFO] Saved sqrt_sigma weights to {weights_sqrt_path}")
    
    # 統計情報を表示
    print("\n" + "=" * 80)
    print("=== 結果サマリー ===")
    print("=" * 80)
    
    ret = results["combined_ret_sqrt"]
    idx = results["combined_index_sqrt"]
    
    print(f"\n【sqrt_sigma】")
    print(f"  データ期間: {ret.index.min().date()} ～ {ret.index.max().date()}")
    print(f"  データ数: {len(ret)}")
    print(f"  累積リターン: {(idx.iloc[-1] - 1) * 100:.2f}%")
    print(f"  年率リターン: {((idx.iloc[-1]) ** (252 / len(ret)) - 1) * 100:.2f}%")
    print(f"  日次リターン平均: {ret.mean() * 100:.4f}%")
    print(f"  日次リターン標準偏差: {ret.std() * 100:.4f}%")
    if ret.std() > 0:
        sharpe = (ret.mean() / ret.std()) * np.sqrt(252)
        print(f"  シャープレシオ: {sharpe:.4f}")
    
    # ウェイト統計
    weights = results["weights_sqrt"]
    print(f"\n  ウェイト統計（平均）:")
    for col in weights.columns:
        print(f"    {col}: {weights[col].mean():.4f} (min: {weights[col].min():.4f}, max: {weights[col].max():.4f})")
    
    print("\n" + "=" * 80)
    print("=== 完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()
