#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/tools/build_inverse_returns.py

1569.T（インバースTOPIX連動ETF）のリターンファイルを生成する

入力:
- data/raw/prices/prices_1569.T.csv

出力:
- data/processed/inverse_returns.parquet（trade_date, ret）
"""

import sys
import io
import os
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32':
    # 環境変数を設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 標準出力のエンコーディングをUTF-8に設定
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.7以前の互換性
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # 既に設定されている場合はスキップ
        pass

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

from scripts.constants import INVERSE_ETF_TICKER

DATA_DIR = Path("data")
RAW_PRICES_DIR = DATA_DIR / "raw" / "prices"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def build_inverse_returns() -> pd.DataFrame:
    """
    1569.Tの価格データからリターンを計算する
    
    Returns
    -------
    pd.DataFrame
        trade_date, ret を含むDataFrame
    """
    # 価格データを読み込む
    price_path = RAW_PRICES_DIR / f"prices_{INVERSE_ETF_TICKER}.csv"
    
    if not price_path.exists():
        raise FileNotFoundError(
            f"価格データファイルが見つかりません: {price_path}\n"
            f"先に download_prices.py --tickers {INVERSE_ETF_TICKER} を実行してください。"
        )
    
    print(f"[INFO] 価格データを読み込み中: {price_path}")
    df = pd.read_csv(price_path)
    
    # 日付をdatetimeに変換
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # adj_closeが存在する場合はそれを使用、なければcloseを使用
    if "adj_close" in df.columns:
        price_col = "adj_close"
    elif "close" in df.columns:
        price_col = "close"
    else:
        raise ValueError(f"価格カラム（closeまたはadj_close）が見つかりません: {df.columns.tolist()}")
    
    # 価格を数値型に変換（文字列の場合があるため）
    df[price_col] = pd.to_numeric(df[price_col], errors='coerce')
    
    # リターンを計算
    df["ret"] = df[price_col].pct_change()
    
    # 結果を整形
    df_result = pd.DataFrame({
        "trade_date": df["date"],
        "ret": df["ret"]
    })
    
    # NaNを削除
    df_result = df_result.dropna().reset_index(drop=True)
    
    print(f"[INFO] リターン計算完了: {len(df_result)} 日分")
    print(f"[INFO] 期間: {df_result['trade_date'].min()} ～ {df_result['trade_date'].max()}")
    print(f"[INFO] 平均リターン: {df_result['ret'].mean():.6f}")
    print(f"[INFO] 標準偏差: {df_result['ret'].std():.6f}")
    
    return df_result


def main():
    """メイン関数"""
    print("=" * 80)
    print(f"=== インバースETFリターンファイル生成 ({INVERSE_ETF_TICKER}) ===")
    print("=" * 80)
    
    try:
        df_returns = build_inverse_returns()
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 保存
    output_path = PROCESSED_DIR / "inverse_returns.parquet"
    df_returns.to_parquet(output_path, index=False)
    print(f"\n[OK] 保存: {output_path}")
    
    print("\n" + "=" * 80)
    print("完了: インバースETFリターンファイル生成完了")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

