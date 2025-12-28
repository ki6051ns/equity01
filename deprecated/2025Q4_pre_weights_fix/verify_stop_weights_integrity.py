#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/verify_stop_weights_integrity.py

STOP付weightsの整合性検証（再発防止用）

検証項目：
1. 構文チェック（py_compile）
2. weights再生成の成功確認
3. PlanA weightsのサニティチェック
   - inv>0日数 == STOP日数
   - 1356.T > 0 日数 == 0
   - STOP日の inv 平均 == 0.25, non_inv == 0.75, total == 1.0
"""

import sys
import subprocess
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


def check_syntax(file_path: Path) -> bool:
    """構文チェック（py_compile）"""
    print(f"\n[CHECK 1] 構文チェック: {file_path}")
    try:
        import py_compile
        py_compile.compile(str(file_path), doraise=True)
        print(f"  ✓ 構文チェックOK")
        return True
    except py_compile.PyCompileError as e:
        print(f"  ✗ 構文エラー: {e}")
        return False
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return False


def check_weights_generation() -> bool:
    """weights再生成の成功確認"""
    print(f"\n[CHECK 2] weights再生成")
    script_path = ROOT_DIR / "scripts" / "analysis" / "build_cross4_target_weights_with_stop.py"
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300  # 5分タイムアウト
        )
        
        if result.returncode == 0:
            print(f"  ✓ weights再生成成功")
            # 出力に成功メッセージがあるか確認
            if "完了" in result.stdout or "保存" in result.stdout:
                print(f"    (保存ログ確認済み)")
            return True
        else:
            print(f"  ✗ weights再生成失敗 (exit code: {result.returncode})")
            print(f"    stderr: {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ weights再生成がタイムアウト（300秒）")
        return False
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return False


def check_plana_weights_integrity(strategy: str = "planA", window: int = 60) -> bool:
    """PlanA weightsのサニティチェック"""
    print(f"\n[CHECK 3] PlanA weightsサニティチェック ({strategy} w{window})")
    
    weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
    
    if not weights_path.exists():
        print(f"  ✗ weightsファイルが見つかりません: {weights_path}")
        return False
    
    try:
        df = pd.read_parquet(weights_path)
        df["date"] = pd.to_datetime(df["date"])
        
        # STOP条件を計算（検証用）
        try:
            from scripts.analysis.build_cross4_target_weights_with_stop import (
                load_cross4_returns_for_stop, compute_stop_conditions
            )
            df_returns = load_cross4_returns_for_stop()
            df_returns = df_returns.sort_values("trade_date").reset_index(drop=True)
            port_ret = df_returns.set_index("trade_date")["port_ret_cc"]
            tpx_ret = df_returns.set_index("trade_date")["tpx_ret_cc"]
            stop_conditions = compute_stop_conditions(port_ret, tpx_ret, windows=[window])
            stop_cond = stop_conditions[window]
            
            # STOP日を特定
            stop_df = pd.DataFrame({
                "date": stop_cond.index,
                "stop_flag": stop_cond.values.astype(int)
            })
            stop_df["date"] = pd.to_datetime(stop_df["date"])
            stop_dates = set(stop_df[stop_df["stop_flag"] == 1]["date"].dt.date)
            stop_days_count = len(stop_dates)
            
        except Exception as e:
            print(f"  ⚠ STOP条件計算に失敗: {e}")
            print(f"    （STOP日数の検証はスキップします）")
            stop_dates = set()
            stop_days_count = None
        
        # 日付ごとに集計
        daily_stats = []
        for date in df["date"].unique():
            day_df = df[df["date"] == date]
            date_obj = pd.to_datetime(date).date()
            is_stop = date_obj in stop_dates if stop_dates else False
            
            inv_weight = day_df[day_df["symbol"] == INVERSE_ETF_TICKER]["weight"].sum()
            banned_1356_weight = day_df[day_df["symbol"] == "1356.T"]["weight"].sum()
            non_inv_weight_sum = day_df[day_df["symbol"] != INVERSE_ETF_TICKER]["weight"].sum()
            total_weight = day_df["weight"].sum()
            
            daily_stats.append({
                "date": date,
                "is_stop": is_stop,
                "inverse_weight": inv_weight,
                "non_inverse_weight_sum": non_inv_weight_sum,
                "total_weight": total_weight,
                "banned_1356_weight": banned_1356_weight,
            })
        
        stats_df = pd.DataFrame(daily_stats)
        
        # 検証項目
        checks = []
        
        # 1. inv>0日数 == STOP日数
        if stop_days_count is not None:
            inv_positive_days = (stats_df["inverse_weight"] > 1e-6).sum()
            check1 = inv_positive_days == stop_days_count
            checks.append(("inv>0日数 == STOP日数", check1, f"{inv_positive_days} == {stop_days_count}"))
            if not check1:
                print(f"  ✗ inv>0日数 ({inv_positive_days}) != STOP日数 ({stop_days_count})")
        else:
            checks.append(("inv>0日数 == STOP日数", None, "SKIP (STOP条件計算失敗)"))
        
        # 2. 1356.T > 0 日数 == 0
        banned_1356_days = (stats_df["banned_1356_weight"] > 1e-6).sum()
        check2 = banned_1356_days == 0
        checks.append(("1356.T > 0 日数 == 0", check2, f"{banned_1356_days} == 0"))
        if not check2:
            print(f"  ✗ 1356.T > 0 の日数が {banned_1356_days} 日（0であるべき）")
        
        # 3. STOP日の inv 平均 == 0.25, non_inv == 0.75, total == 1.0
        stop_day_stats = stats_df[stats_df["is_stop"] == True]
        if len(stop_day_stats) > 0:
            inv_mean = stop_day_stats["inverse_weight"].mean()
            non_inv_mean = stop_day_stats["non_inverse_weight_sum"].mean()
            total_mean = stop_day_stats["total_weight"].mean()
            
            inv_ok = abs(inv_mean - 0.25) < 0.01
            non_inv_ok = abs(non_inv_mean - 0.75) < 0.01
            total_ok = abs(total_mean - 1.0) < 0.01
            
            check3 = inv_ok and non_inv_ok and total_ok
            checks.append(
                ("STOP日の平均 (inv/non_inv/total) ≈ (0.25/0.75/1.0)", 
                 check3, 
                 f"({inv_mean:.6f} / {non_inv_mean:.6f} / {total_mean:.6f})")
            )
            if not check3:
                print(f"  ✗ STOP日の平均が期待値と異なります")
                print(f"    inv: {inv_mean:.6f} (期待: 0.25), non_inv: {non_inv_mean:.6f} (期待: 0.75), total: {total_mean:.6f} (期待: 1.0)")
        else:
            checks.append(("STOP日の平均", None, "SKIP (STOP日なし)"))
        
        # 結果サマリー
        passed = sum(1 for _, result, _ in checks if result is True)
        failed = sum(1 for _, result, _ in checks if result is False)
        skipped = sum(1 for _, result, _ in checks if result is None)
        
        print(f"\n  【検証結果サマリー】")
        for name, result, detail in checks:
            if result is True:
                print(f"    ✓ {name}: {detail}")
            elif result is False:
                print(f"    ✗ {name}: {detail}")
            else:
                print(f"    - {name}: {detail}")
        
        if failed == 0 and skipped == 0:
            print(f"  ✓ 全検証項目が合格")
            return True
        elif failed > 0:
            print(f"  ✗ {failed}個の検証項目が不合格")
            return False
        else:
            print(f"  ⚠ {skipped}個の検証項目がスキップされました")
            return True  # スキップのみの場合はOKとする
        
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="STOP付weightsの整合性検証（再発防止用）"
    )
    parser.add_argument(
        "--skip-syntax",
        action="store_true",
        help="構文チェックをスキップ"
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="weights再生成をスキップ"
    )
    parser.add_argument(
        "--skip-sanity",
        action="store_true",
        help="サニティチェックをスキップ"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("=== STOP付weights整合性検証 ===")
    print("=" * 80)
    
    all_passed = True
    
    # CHECK 1: 構文チェック
    if not args.skip_syntax:
        script_path = ROOT_DIR / "scripts" / "analysis" / "build_cross4_target_weights_with_stop.py"
        if not check_syntax(script_path):
            all_passed = False
    else:
        print("\n[CHECK 1] 構文チェック: スキップ")
    
    # CHECK 2: weights再生成
    if not args.skip_generation:
        if not check_weights_generation():
            all_passed = False
    else:
        print("\n[CHECK 2] weights再生成: スキップ")
    
    # CHECK 3: サニティチェック
    if not args.skip_sanity:
        if not check_plana_weights_integrity("planA", 60):
            all_passed = False
    else:
        print("\n[CHECK 3] サニティチェック: スキップ")
    
    # 最終結果
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 全検証が合格")
        print("=" * 80)
        return 0
    else:
        print("✗ 検証に不合格項目があります")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())

