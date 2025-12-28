#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/build_cross4_target_weights.py

cross4 target weights を生成する（analysis内で完結、coreへ書き戻し禁止）

入力:
- data/processed/weights/h{H}_{ladder}_{variant}.parquet（generate_variant_weights.pyの出力）

出力（研究用）:
- data/processed/weights/cross4_target_weights.parquet（date, symbol, weight）
- data/processed/weights/cross4_target_weights_latest.parquet（最新日のみ、Executionインターフェース想定）

合成ロジック:
- Variant合成: w_cross4_h = 0.75 * w_rank_only_h + 0.25 * w_zdownvol_h
- Horizon合成: w_cross4 = Σ_h (horizon_weight[h] * w_cross4_h)
- 正規化: sum(w_cross4)=1（ロングオンリー前提）

重要: この段階ではまだprdに接続しない。まずanalysis内で一致検証。
"""

import sys
from pathlib import Path
from typing import Dict, Tuple

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/build_cross4_target_weights.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

# 設定を直接定義（ensemble_variant_cross4.pyはdeprecatedに移動したため）
VARIANTS = {
    "rank": "rank_only (Variant B)",
    "zdownvol": "z_downvol (Variant E)",
}
VARIANT_WEIGHTS = {
    "rank": 0.75,  # Variant B (rank_only)
    "zdownvol": 0.25,  # Variant E (z_downvol)
}
HORIZON_WEIGHTS = {
    (1, "nonladder"): 0.15,
    (5, "nonladder"): 0.15,
    (10, "nonladder"): 0.20,
    (60, "ladder"): 0.10,
    (90, "ladder"): 0.20,
    (120, "ladder"): 0.20,
}

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)


def load_horizon_variant_weights(h: int, ladder_type: str, variant_key: str) -> pd.DataFrame:
    """
    variant別/horizon別の日次weightsを読み込む
    
    Parameters
    ----------
    h : int
        ホライゾン
    ladder_type : str
        "ladder" または "nonladder"
    variant_key : str
        "rank" または "zdownvol"
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    if variant_key == "rank":
        suffix = "rank_only"
    elif variant_key == "zdownvol":
        suffix = "zdownvol"
    else:
        raise ValueError(f"Unknown variant_key: {variant_key}")
    
    weights_path = WEIGHTS_DIR / f"h{h}_{ladder_type}_{suffix}.parquet"
    
    if weights_path.exists():
        df = pd.read_parquet(weights_path)
        if len(df) > 0:
            return df
    else:
        # weightsファイルが存在しない場合は空DataFrameを返す
        print(f"  ⚠️  H{h} ({ladder_type}) {variant_key}: weightsファイルが見つかりません: {weights_path}")
        return pd.DataFrame()
    
    return pd.DataFrame()


def average_variants_for_horizon_weights(
    h: int, ladder_type: str, variant_dict: dict, variant_weights: dict
) -> pd.DataFrame:
    """
    ホライゾン内で複数のVariantのweightsを重み付き平均化（B 75% / E 25%）
    
    Parameters
    ----------
    h : int
        ホライゾン
    ladder_type : str
        "ladder" または "nonladder"
    variant_dict : dict
        Variant辞書
    variant_weights : dict
        Variant内ウェイト（{"rank": 0.75, "zdownvol": 0.25}）
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame（Variant重み付き平均済み）
    """
    dfs = {}
    loaded_variants = []
    
    for variant_key, variant_name in variant_dict.items():
        df = load_horizon_variant_weights(h, ladder_type, variant_key)
        if not df.empty:
            dfs[variant_key] = df
            loaded_variants.append(f"{variant_name} ({variant_weights.get(variant_key, 0.0):.0%})")
    
    if len(dfs) == 0:
        print(f"  ⚠️  H{h} ({ladder_type}): 読み込めるVariant weightsがありません")
        return pd.DataFrame()
    
    print(f"  H{h} ({ladder_type}): {len(loaded_variants)} Variant weightsを重み付き平均化 ({', '.join(loaded_variants)})")
    
    # 日付とsymbolでマージ
    merged = None
    for variant_key, df in dfs.items():
        weight = variant_weights.get(variant_key, 0.0)
        if weight > 0:
            df_weighted = df[["date", "symbol", "weight"]].copy()
            df_weighted["weight"] = df_weighted["weight"] * weight
            
            if merged is None:
                merged = df_weighted
            else:
                merged = pd.merge(
                    merged, df_weighted,
                    on=["date", "symbol"],
                    how="outer",
                    suffixes=("", f"_{variant_key}")
                )
    
    if merged is None:
        return pd.DataFrame()
    
    # 重み付き平均を計算
    weight_cols = [c for c in merged.columns if c.startswith("weight")]
    if len(weight_cols) > 0:
        merged["weight"] = merged[weight_cols].sum(axis=1, skipna=True)
        merged = merged.drop(columns=[c for c in weight_cols if c != "weight"])
        merged["weight"] = merged["weight"].fillna(0.0)
    
    # 日付ごとに正規化（合計=1.0）
    merged = merged.groupby("date", group_keys=False).apply(
        lambda g: g.assign(weight=g["weight"] / g["weight"].sum() if g["weight"].sum() > 0 else 0.0)
    )
    
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)


def combine_horizons_weights(
    horizon_data: Dict[Tuple[int, str], pd.DataFrame],
    horizon_weights: Dict[Tuple[int, str], float]
) -> pd.DataFrame:
    """
    ホライゾン間でweightsを重み付き合成
    
    Parameters
    ----------
    horizon_data : Dict[Tuple[int, str], pd.DataFrame]
        ホライゾン別のweights（(h, ladder_type) -> DataFrame）
    horizon_weights : Dict[Tuple[int, str], float]
        ホライゾン別ウェイト
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame（ホライゾン重み付き合成済み）
    """
    merged = None
    
    for (h, ladder_type), df_h in horizon_data.items():
        if df_h.empty:
            continue
        
        weight = horizon_weights.get((h, ladder_type), 0.0)
        if weight > 0:
            df_weighted = df_h[["date", "symbol", "weight"]].copy()
            df_weighted["weight"] = df_weighted["weight"] * weight
            
            if merged is None:
                merged = df_weighted
            else:
                merged = pd.merge(
                    merged, df_weighted,
                    on=["date", "symbol"],
                    how="outer",
                    suffixes=("", f"_h{h}_{ladder_type}")
                )
    
    if merged is None:
        return pd.DataFrame()
    
    # 重み付き合成
    weight_cols = [c for c in merged.columns if c.startswith("weight")]
    if len(weight_cols) > 0:
        merged["weight"] = merged[weight_cols].sum(axis=1, skipna=True)
        merged = merged.drop(columns=[c for c in weight_cols if c != "weight"])
        merged["weight"] = merged["weight"].fillna(0.0)
    
    # 日付ごとに正規化（合計=1.0）
    merged = merged.groupby("date", group_keys=False).apply(
        lambda g: g.assign(weight=g["weight"] / g["weight"].sum() if g["weight"].sum() > 0 else 0.0)
    )
    
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== cross4 Target Weights 生成（weights版） ===")
    print("=" * 80)
    print("\nVariant内ウェイト:")
    for variant_key, w in sorted(VARIANT_WEIGHTS.items()):
        variant_name = VARIANTS.get(variant_key, variant_key)
        print(f"  {variant_name}: {w:.2%}")
    
    print("\n全ホライゾン（Variant B 75% / E 25%）:")
    for (h, lad), w in sorted(HORIZON_WEIGHTS.items()):
        mode = "ラダー" if lad == "ladder" else "非ラダー"
        print(f"  H{h} ({mode}): {w:.2%}")
    
    print("\n[STEP 1] 各ホライゾンのVariant重み付き平均化中...")
    horizon_data = {}
    
    for (h, ladder_type), horizon_weight in HORIZON_WEIGHTS.items():
        df_h = average_variants_for_horizon_weights(h, ladder_type, VARIANTS, VARIANT_WEIGHTS)
        if not df_h.empty:
            horizon_data[(h, ladder_type)] = df_h
            print(f"  ✓ H{h} ({ladder_type}): {len(df_h)} rows")
        else:
            print(f"  ⚠️  H{h} ({ladder_type}): データなし")
    
    if len(horizon_data) == 0:
        print("\n[ERROR] 読み込めるホライゾンデータがありません。")
        print("先に generate_variant_weights.py を実行してweightsを生成してください。")
        print("例:")
        print("  python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder")
        print("  python scripts/analysis/generate_variant_weights.py --variant zdownvol --horizon 1 --ladder nonladder")
        print("  # ... 他のhorizonも同様に実行")
        return
    
    print("\n[STEP 2] ホライゾン間でweightsを重み付き合成中...")
    df_cross4 = combine_horizons_weights(horizon_data, HORIZON_WEIGHTS)
    
    if df_cross4.empty:
        print("\n[ERROR] cross4 weightsの合成に失敗しました。")
        return
    
    print(f"  ✓ 合成完了: {len(df_cross4)} rows")
    
    # 保存（全期間）
    # 出力ファイル名を固定: data/processed/weights/cross4_target_weights.parquet
    output_path = WEIGHTS_DIR / "cross4_target_weights.parquet"
    df_cross4.to_parquet(output_path, index=False)
    print(f"\n✓ cross4 target weights（全期間）を保存: {output_path}")
    
    # 保存（最新日のみ）
    latest_date = df_cross4["date"].max()
    df_latest = df_cross4[df_cross4["date"] == latest_date].copy()
    latest_path = WEIGHTS_DIR / "cross4_target_weights_latest.parquet"
    df_latest.to_parquet(latest_path, index=False)
    print(f"✓ cross4 target weights（最新日: {latest_date}）を保存: {latest_path}")
    
    # 検証
    weight_sum = df_latest["weight"].sum()
    print(f"\n[検証] 最新日のweight合計: {weight_sum:.6f} (期待値: 1.0)")
    if abs(weight_sum - 1.0) > 0.01:
        print("  ⚠️  警告: weight合計が1.0から大きくずれています")
    else:
        print("  ✓ OK")
    
    print("\n" + "=" * 80)
    print("完了: cross4 target weights生成完了")
    print("=" * 80)


if __name__ == "__main__":
    main()

