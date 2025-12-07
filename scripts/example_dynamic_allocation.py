#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/example_dynamic_allocation.py

動的ウェイト計算の使用例

4スリーブ（rank_only, cross3, minvar, inverse）の動的配分を計算する例。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from alloc.dynamic_allocation import compute_dynamic_weights


def main():
    """
    使用例: 4スリーブの動的配分
    
    注意: 実際のリターンデータが必要です。
    この例では、データの読み込み方法を示します。
    """
    
    # 例: 各スリーブのリターンデータを読み込む
    # 実際のデータパスに置き換えてください
    data_dir = Path("data/processed")
    
    # リターンデータの準備（例）
    # 実際には、各スリーブの日次リターンを結合したDataFrameが必要です
    # returns_df = pd.DataFrame({
    #     "rank_only": ...,
    #     "cross3": ...,
    #     "minvar": ...,
    #     "inverse": ...,
    # })
    
    # 事前ウェイトの設定
    priors = {
        "rank_only": 0.45,
        "cross3": 0.25,
        "minvar": 0.20,
        "inverse": 0.10,
    }
    
    # ウェイトの上下限
    bounds = {
        "rank_only": (0.30, 0.60),
        "cross3": (0.15, 0.40),
        "minvar": (0.10, 0.35),
        "inverse": (0.00, 0.20),
    }
    
    # √σベースの動的ウェイト計算
    # weights_sqrt = compute_dynamic_weights(
    #     returns=returns_df,
    #     window=252,
    #     priors=priors,
    #     bounds=bounds,
    #     method="sqrt_sigma",
    # )
    
    # σベースの動的ウェイト計算
    # weights_sigma = compute_dynamic_weights(
    #     returns=returns_df,
    #     window=252,
    #     priors=priors,
    #     bounds=bounds,
    #     method="sigma",
    # )
    
    # 結果の保存例
    # weights_sqrt.to_parquet(data_dir / "dynamic_weights_sqrt_sigma.parquet")
    # weights_sigma.to_parquet(data_dir / "dynamic_weights_sigma.parquet")
    
    print("使用例:")
    print("1. 各スリーブの日次リターンを含むDataFrameを準備")
    print("2. compute_dynamic_weights() を呼び出す")
    print("3. 結果のウェイトDataFrameを使って合成リターンを計算")
    print("\n詳細は alloc/dynamic_allocation.py のdocstringを参照してください。")


if __name__ == "__main__":
    main()

