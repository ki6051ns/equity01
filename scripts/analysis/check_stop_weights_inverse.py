#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/check_stop_weights_inverse.py

STOP付weightsファイルでインバースETF（1569.T）のweightが正しく設定されているか確認

用途: PlanA weightsでSTOP日に1569.Tが0.25入っているか、誤って1356.Tに入っていないか確認
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from scripts.constants import INVERSE_ETF_TICKER

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"


def check_inverse_weights(strategy: str, window: int):
    """
    STOP付weightsファイルでインバースETFのweightを確認
    
    Parameters
    ----------
    strategy : str
        "planA", "stop0", "planB" のいずれか
    window : int
        ウィンドウサイズ（60, 120）
    """
    weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        print(f"[ERROR] ファイルが見つかりません: {weights_path}")
        return
    
    print("=" * 80)
    print(f"【インバースETF Weight確認: {strategy.upper()} w{window}】")
    print("=" * 80)
    print(f"\nファイル: {weights_path}")
    print(f"インバースETF ticker: {INVERSE_ETF_TICKER}")
    
    df = pd.read_parquet(weights_path)
    df["date"] = pd.to_datetime(df["date"])
    
    # 日付ごとに集計
    daily_stats = []
    for date in df["date"].unique():
        day_df = df[df["date"] == date]
        inv_weight = day_df[day_df["symbol"] == INVERSE_ETF_TICKER]["weight"].sum()
        other_1356_weight = day_df[day_df["symbol"] == "1356.T"]["weight"].sum()
        total_weight = day_df["weight"].sum()
        non_inv_weight = day_df[day_df["symbol"] != INVERSE_ETF_TICKER]["weight"].sum()
        
        daily_stats.append({
            "date": date,
            "inverse_weight": inv_weight,
            "non_inverse_weight": non_inv_weight,
            "total_weight": total_weight,
            "other_1356_weight": other_1356_weight,
            "has_inverse": inv_weight > 0.0,
        })
    
    stats_df = pd.DataFrame(daily_stats)
    
    # 統計サマリー
    print(f"\n【統計サマリー】")
    print(f"  総日数: {len(stats_df)}")
    print(f"  インバースETF weight > 0 の日数: {stats_df['has_inverse'].sum()}")
    print(f"  1356.T weight > 0 の日数: {(stats_df['other_1356_weight'] > 0).sum()}")
    
    if strategy == "planA":
        print(f"\n【PlanA期待値チェック】")
        inv_days = stats_df[stats_df["has_inverse"]]
        if len(inv_days) > 0:
            avg_inv_weight = inv_days["inverse_weight"].mean()
            avg_non_inv_weight = inv_days["non_inverse_weight"].mean()
            avg_total_weight = inv_days["total_weight"].mean()
            
            print(f"  インバースETF weight > 0 の日数: {len(inv_days)}")
            print(f"  平均インバースweight: {avg_inv_weight:.6f} (期待値: 0.25)")
            print(f"  平均非インバースweight: {avg_non_inv_weight:.6f} (期待値: 0.75)")
            print(f"  平均合計weight: {avg_total_weight:.6f} (期待値: 1.0)")
            
            if abs(avg_inv_weight - 0.25) > 0.01:
                print(f"  ⚠ インバースweightが期待値と大きく異なります（差分: {abs(avg_inv_weight - 0.25):.6f}）")
            else:
                print(f"  ✓ インバースweightは期待値と一致（許容誤差内）")
            
            if abs(avg_total_weight - 1.0) > 0.01:
                print(f"  ⚠ 合計weightが期待値と大きく異なります（差分: {abs(avg_total_weight - 1.0):.6f}）")
            else:
                print(f"  ✓ 合計weightは期待値と一致（許容誤差内）")
        else:
            print(f"  ⚠ インバースETF weight > 0 の日がありません（PlanAでは異常）")
    
    # 最新日の詳細
    latest_date = stats_df["date"].max()
    latest_stats = stats_df[stats_df["date"] == latest_date].iloc[0]
    
    print(f"\n【最新日（{latest_date.date()}）の詳細】")
    print(f"  インバースETF weight: {latest_stats['inverse_weight']:.6f}")
    print(f"  非インバースweight: {latest_stats['non_inverse_weight']:.6f}")
    print(f"  合計weight: {latest_stats['total_weight']:.6f}")
    print(f"  1356.T weight: {latest_stats['other_1356_weight']:.6f}")
    
    if latest_stats['other_1356_weight'] > 0:
        print(f"  ⚠ 1356.Tにweightが入っています（{INVERSE_ETF_TICKER}を使用すべき）")
    
    # インバースweight > 0 の日の詳細（Top10）
    inv_days = stats_df[stats_df["has_inverse"]].nlargest(10, "inverse_weight")
    if len(inv_days) > 0:
        print(f"\n【インバースweightが大きい日 Top10】")
        print(inv_days[["date", "inverse_weight", "non_inverse_weight", "total_weight"]].to_string(index=False, float_format="%.6f"))
    
    print("\n" + "=" * 80)


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="STOP付weightsファイルでインバースETFのweightを確認"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="planA",
        choices=["planA", "stop0", "planB"],
        help="戦略（planA, stop0, planB）"
    )
    parser.add_argument(
        "--window",
        type=int,
        default=60,
        choices=[60, 120],
        help="ウィンドウサイズ（60, 120）"
    )
    
    args = parser.parse_args()
    
    check_inverse_weights(args.strategy, args.window)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

