"""
統合評価スクリプト（完全統合型ダッシュボード）

このスクリプトを実行すると、以下が順番に実行されます：
- 単体版（baseline, H=1）
- ホライゾン別（H=5, 10, 20, 60）
- アンサンブル版
- 月次・年次サマリ
- rolling α

使い方:
    python scripts/run_equity01_eval.py
    python scripts/run_equity01_eval.py --horizon-ensemble

【運用ルール】
- 基本は run_equity01_eval.py 以外から実行しない運用ルールにする
- 単体テスト以外は、評価も分析も全部 run_equity01_eval.py 経由で実行
- 手計算したくなったときも、まず run_equity01_eval.py を実行してから Parquet を読む
- これにより、TOPIXデータの更新漏れや日付不整合を防げる
"""
import argparse
from pathlib import Path
import os
import sys
from typing import List, Dict

import numpy as np
import pandas as pd

# scripts ディレクトリをパスに追加
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from scripts.tools.build_index_tpx_daily import main as build_index_main
from scripts.core.calc_alpha_beta import main as calc_alpha_main

WINDOWS = [10, 20, 60, 120]


def compute_rolling_relative_alpha(df_alpha: pd.DataFrame, label: str = "") -> pd.DataFrame:
    """
    moving window 相対αを計算（DataFrame版）
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date").reset_index(drop=True)
    
    if not {"port_ret_cc", "tpx_ret_cc"}.issubset(df.columns):
        raise KeyError(
            f"必要な列 'port_ret_cc', 'tpx_ret_cc' が見つかりません: {df.columns.tolist()}"
        )
    
    port = df["port_ret_cc"].astype(float)
    tpx = df["tpx_ret_cc"].astype(float)
    
    out = df[["trade_date"]].copy()
    
    for w in WINDOWS:
        port_cum = (1.0 + port).rolling(w, min_periods=1).apply(np.prod, raw=True)
        tpx_cum = (1.0 + tpx).rolling(w, min_periods=1).apply(np.prod, raw=True)
        
        out[f"port_cum_{w}d"] = port_cum
        out[f"tpx_cum_{w}d"] = tpx_cum
        out[f"rel_alpha_{w}d"] = port_cum - tpx_cum
    
    if label:
        out_path = Path(f"data/processed/rolling_relative_alpha_{label}.parquet")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path, index=False)
    
    return out


# 注意: 詳細なサマリ表示機能（print_baseline_summary, print_horizon_summary など）は
# analysis/run_eval_report.py に移行しました。


# 注意: 完全統合型評価パイプライン（月次集計・ホライゾンアンサンブル含む）は
# analysis/run_eval_report.py に移行しました。
# このファイルは core 直下で完結する最小評価のみを提供します。


def main() -> None:
    parser = argparse.ArgumentParser(description="equity01 統合評価パイプライン")
    parser.add_argument(
        "--horizon-ensemble",
        action="store_true",
        help="ホライゾンアンサンブルを含む完全統合評価を実行する",
    )
    args = parser.parse_args()
    
    # ホライゾンアンサンブルモード（完全統合版）
    # 注意: この機能は analysis/run_eval_report.py に移行しました
    if args.horizon_ensemble:
        print("[WARN] --horizon-ensemble オプションは analysis/run_eval_report.py に移行しました")
        print("  実行方法: python deprecated/2025Q4_pre_weights_fix/run_eval_report.py --horizon-ensemble (deprecated)")
        sys.exit(0)
    
    # 通常の評価パイプライン（従来版）
    print("=" * 60)
    print("equity01 評価パイプライン実行")
    print("=" * 60)
    
    print("\n=== STEP 1: build_index_tpx_daily ===")
    try:
        build_index_main()
        print("[OK] TOPIXリターン更新完了")
    except Exception as e:
        print(f"[ERROR] TOPIXリターン更新失敗: {e}")
        raise
    
    print("\n=== STEP 2: calc_alpha_beta ===")
    try:
        calc_alpha_main()
        print("[OK] ペーパートレード + 相対α計算完了")
    except Exception as e:
        print(f"[ERROR] ペーパートレード + 相対α計算失敗: {e}")
        raise
    
    print("\n=== STEP 3: rolling_relative_alpha ===")
    try:
        # 通常モード用のrolling alpha計算
        src = Path("data/processed/paper_trade_with_alpha_beta.parquet")
        if src.exists():
            df_alpha = pd.read_parquet(src)
            compute_rolling_relative_alpha(df_alpha, label="")
            print("[OK] moving window 相対α計算完了")
        else:
            print("[WARN] paper_trade_with_alpha_beta.parquet が見つかりません。スキップします。")
    except Exception as e:
        print(f"[ERROR] moving window 相対α計算失敗: {e}")
        raise
    
    print("\n=== STEP 4: 基本評価完了 ===")
    print("[OK] 基本評価パイプライン完了")
    print("\n注意: 月次集計・ホライゾンアンサンブルは別コマンドで実行してください:")
    print("  python deprecated/2025Q4_pre_weights_fix/run_eval_report.py (deprecated)")
    
    print("\n" + "=" * 60)
    print("全ての処理が完了しました！")
    print("=" * 60)


if __name__ == "__main__":
    main()
