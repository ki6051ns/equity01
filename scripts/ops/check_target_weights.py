#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/ops/check_target_weights.py

運用終点ファイル（daily_portfolio_guarded.parquet）の内容を確認するユーティリティ。

確認項目:
- symbol / weight / date が揃っている
- weight が合計1（または仕様通り）
- 0やNaNや重複がない
- 最新日が存在する
"""

from pathlib import Path
import sys

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np


def check_target_weights(parquet_path: Path = None) -> dict:
    """
    運用終点ファイル（daily_portfolio_guarded.parquet）の内容を確認する。
    
    Parameters
    ----------
    parquet_path : Path, optional
        確認するparquetファイルのパス。デフォルトは data/processed/daily_portfolio_guarded.parquet
    
    Returns
    -------
    dict
        確認結果の辞書
    """
    if parquet_path is None:
        parquet_path = Path("data/processed/daily_portfolio_guarded.parquet")
    
    if not parquet_path.exists():
        return {
            "status": "ERROR",
            "message": f"ファイルが見つかりません: {parquet_path}",
            "checks": {}
        }
    
    # 読み込み
    df = pd.read_parquet(parquet_path)
    
    checks = {}
    
    # 1. 必須カラムの確認
    required_cols = ["date", "symbol", "weight"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    checks["required_columns"] = {
        "status": "PASS" if len(missing_cols) == 0 else "FAIL",
        "missing": missing_cols,
        "message": f"必須カラム確認: {required_cols}"
    }
    
    if len(missing_cols) > 0:
        return {
            "status": "ERROR",
            "message": f"必須カラムが不足しています: {missing_cols}",
            "checks": checks
        }
    
    # 2. 日付の確認
    df["date"] = pd.to_datetime(df["date"])
    latest_date = df["date"].max()
    checks["latest_date"] = {
        "status": "PASS",
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "message": f"最新日: {latest_date.strftime('%Y-%m-%d')}"
    }
    
    # 3. 最新日のデータ確認
    df_latest = df[df["date"] == latest_date].copy()
    checks["latest_date_rows"] = {
        "status": "PASS",
        "count": len(df_latest),
        "message": f"最新日の行数: {len(df_latest)}"
    }
    
    # 4. weight の確認
    weight_sum = df_latest["weight"].sum()
    weight_min = df_latest["weight"].min()
    weight_max = df_latest["weight"].max()
    weight_nan_count = df_latest["weight"].isna().sum()
    weight_zero_count = (df_latest["weight"] == 0).sum()
    
    checks["weight_sum"] = {
        "status": "PASS" if abs(weight_sum - 1.0) < 0.01 else "WARN",
        "value": weight_sum,
        "message": f"最新日のweight合計: {weight_sum:.6f} (期待値: 1.0)"
    }
    
    checks["weight_range"] = {
        "status": "PASS",
        "min": weight_min,
        "max": weight_max,
        "message": f"最新日のweight範囲: [{weight_min:.6f}, {weight_max:.6f}]"
    }
    
    checks["weight_nan"] = {
        "status": "PASS" if weight_nan_count == 0 else "FAIL",
        "count": weight_nan_count,
        "message": f"最新日のweight NaN数: {weight_nan_count}"
    }
    
    checks["weight_zero"] = {
        "status": "WARN" if weight_zero_count > 0 else "PASS",
        "count": weight_zero_count,
        "message": f"最新日のweight=0の数: {weight_zero_count}"
    }
    
    # 5. 重複の確認
    dup_count = df_latest.duplicated(subset=["symbol"]).sum()
    checks["duplicates"] = {
        "status": "PASS" if dup_count == 0 else "FAIL",
        "count": dup_count,
        "message": f"最新日のsymbol重複数: {dup_count}"
    }
    
    # 6. symbol の確認
    symbol_count = df_latest["symbol"].nunique()
    checks["symbol_count"] = {
        "status": "PASS",
        "count": symbol_count,
        "message": f"最新日のユニークsymbol数: {symbol_count}"
    }
    
    # 全体のstatusを決定
    overall_status = "PASS"
    for check_name, check_result in checks.items():
        if check_result["status"] == "FAIL":
            overall_status = "FAIL"
            break
        elif check_result["status"] == "WARN" and overall_status == "PASS":
            overall_status = "WARN"
    
    return {
        "status": overall_status,
        "message": f"確認完了: {overall_status}",
        "checks": checks,
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "file_path": str(parquet_path)
    }


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="運用終点ファイル（daily_portfolio_guarded.parquet）の内容を確認する"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="data/processed/daily_portfolio_guarded.parquet",
        help="確認するparquetファイルのパス"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細な情報を表示"
    )
    
    args = parser.parse_args()
    
    result = check_target_weights(Path(args.file))
    
    print(f"\n=== 確認結果 ===")
    print(f"ファイル: {result['file_path']}")
    print(f"ステータス: {result['status']}")
    print(f"最新日: {result.get('latest_date', 'N/A')}")
    print(f"\n=== 詳細確認 ===")
    
    for check_name, check_result in result["checks"].items():
        status_icon = {
            "PASS": "✓",
            "WARN": "⚠",
            "FAIL": "✗"
        }.get(check_result["status"], "?")
        
        print(f"{status_icon} {check_name}: {check_result['message']}")
        
        if args.verbose and "value" in check_result:
            print(f"   値: {check_result['value']}")
        if args.verbose and "count" in check_result:
            print(f"   数: {check_result['count']}")
    
    print(f"\n=== サマリ ===")
    print(f"ステータス: {result['status']}")
    
    # 終了コード
    if result["status"] == "FAIL":
        sys.exit(1)
    elif result["status"] == "WARN":
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

