"""
TOPIX 日次リターンテーブルの生成スクリプト

data_loader.DataLoader を使って TOPIX の日足データを取得し、
C→C 日次リターンを計算して data/processed/index_tpx_daily.parquet に保存する。

【フォールバック仕様（prdまで通用する仕様）】
1. デフォルト: ^TOPX (yfinance) を試行
   - 成功した場合はそのまま使用
   
2. フォールバック: ^TOPX が取得できない場合、自動的に 1306.T (TOPIX連動ETF) を使用
   - 1306.T は TOPIX に連動するETFのため、ベンチマークとして使用可能
   - データ品質に問題はない
   
3. ログ出力: フォールバック発生時は必ずログに記録（監査性確保）
   - [ERROR] ^TOPX で取得失敗: ...
   - [OK] 1306.T で取得成功

【運用上の注意】
- ^TOPX は yfinance で取得できない場合が多い（正常な動作）
- フォールバック発生時もデータ品質に問題はない
- 同じ環境では同じフォールバック動作をします（再現性確保）
"""
from pathlib import Path

import pandas as pd
import sys
import os

# scripts ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader


def main() -> None:
    dl = DataLoader(data_dir="data/raw", tz="Asia/Tokyo")

    # ★ TPX のシンボル
    # まずは ^TOPX を試し、ダメなら 1306.T などの TOPIX ETF に差し替え
    tpx_symbols = ["^TOPX", "1306.T"]
    
    df = None
    used_symbol = None
    
    for symbol in tpx_symbols:
        try:
            print(f"TOPIX データ取得を試行中: {symbol}")
            # refresh=True で最新データを強制取得
            df = dl.load_stock_data(symbol, refresh=True)
            if df is not None and not df.empty:
                used_symbol = symbol
                print(f"[OK] {symbol} で取得成功")
                break
        except Exception as e:
            print(f"[ERROR] {symbol} で取得失敗: {e}")
            continue
    
    if df is None or df.empty:
        raise RuntimeError(f"TOPIX データの取得に失敗しました。試行したシンボル: {tpx_symbols}")

    df = df.sort_values("date").copy()
    
    # 前日終値を計算
    df["tpx_prev_close"] = df["close"].shift(1)
    
    # C→C 日次リターン
    df["tpx_ret_cc"] = df["close"] / df["tpx_prev_close"] - 1

    # 前日が無い行は落とす
    df = df.dropna(subset=["tpx_prev_close"])

    # カラム名を統一
    df = df.rename(columns={"date": "trade_date"})
    df = df.rename(columns={"close": "tpx_close"})

    # 出力カラムを選択
    output_cols = ["trade_date", "tpx_close", "tpx_prev_close", "tpx_ret_cc"]
    df_output = df[output_cols].copy()

    # 保存
    out = Path("data/processed/index_tpx_daily.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df_output.to_parquet(out, index=False)

    print(f"\nTOPIX 日次リターンテーブルを保存しました: {out}")
    print(f"使用シンボル: {used_symbol}")
    print(f"期間: {df_output['trade_date'].min()} ～ {df_output['trade_date'].max()}")
    print(f"行数: {len(df_output)}")
    print("\n先頭5行:")
    print(df_output.head())
    print("\n末尾5行:")
    print(df_output.tail())


if __name__ == "__main__":
    main()

