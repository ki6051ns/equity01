#!/usr/bin/env python
"""
診断スクリプト: 指定日のprices欠落の根因特定

入力:
- asof (例: 2025-12-29)
- universe_path (latest_universe.parquet または history/YYYYMMDD_universe.parquet)

出力:
- universe銘柄一覧
- pricesに当日が存在する銘柄/しない銘柄
- 欠落銘柄の「最終日付」（12/26で止まってる等）
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
import argparse

# パス設定
SCRIPT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.tools.lib import data_loader


def check_universe(universe_path: Path, asof: str):
    """universeファイルの確認"""
    if not universe_path.exists():
        print(f"[ERROR] universeファイルが見つかりません: {universe_path}")
        return None
    
    df_uni = pd.read_parquet(universe_path)
    print("=" * 60)
    print("=== universe 確認 ===")
    print("=" * 60)
    print(f"\n【universeファイル】")
    print(f"  パス: {universe_path}")
    print(f"  行数: {len(df_uni)}")
    
    if "ticker" in df_uni.columns:
        symbols = sorted(df_uni["ticker"].unique().tolist())
    elif "symbol" in df_uni.columns:
        symbols = sorted(df_uni["symbol"].unique().tolist())
    else:
        print("[ERROR] universeにticker/symbol列が見つかりません")
        return None
    
    print(f"  銘柄数: {len(symbols)}")
    print(f"  銘柄一覧: {symbols}")
    
    if "asof" in df_uni.columns:
        asof_in_file = df_uni["asof"].iloc[0] if len(df_uni) > 0 else None
        print(f"  asof: {asof_in_file}")
    
    return symbols


def check_prices(symbols: list, asof: str):
    """pricesデータの確認"""
    print("\n" + "=" * 60)
    print("=== prices 確認 ===")
    print("=" * 60)
    
    asof_date = pd.to_datetime(asof)
    
    # 価格データを読み込み
    prices = data_loader.load_prices()
    prices["date"] = pd.to_datetime(prices["date"])
    
    print(f"\n【対象日: {asof}】")
    print(f"  対象銘柄数: {len(symbols)}")
    
    # 各銘柄の12/29データの有無を確認
    symbols_with_data = []
    symbols_missing = []
    missing_details = []
    
    for symbol in symbols:
        symbol_prices = prices[prices["symbol"] == symbol].copy()
        
        if len(symbol_prices) == 0:
            symbols_missing.append(symbol)
            missing_details.append({
                "symbol": symbol,
                "reason": "NO_DATA",
                "latest_date": None,
                "row_count": 0
            })
            continue
        
        # 12/29のデータがあるか
        has_asof = (symbol_prices["date"] == asof_date).any()
        
        if has_asof:
            symbols_with_data.append(symbol)
        else:
            symbols_missing.append(symbol)
            latest_date = symbol_prices["date"].max()
            row_count = len(symbol_prices)
            missing_details.append({
                "symbol": symbol,
                "reason": "MISSING_ASOF",
                "latest_date": latest_date.strftime("%Y-%m-%d") if pd.notna(latest_date) else None,
                "row_count": row_count
            })
    
    print(f"\n【結果サマリー】")
    print(f"  データあり: {len(symbols_with_data)}銘柄")
    print(f"  データなし: {len(symbols_missing)}銘柄")
    
    print(f"\n【データありの銘柄】")
    if symbols_with_data:
        for s in symbols_with_data:
            print(f"    {s}")
    else:
        print("    (なし)")
    
    print(f"\n【データなしの銘柄】")
    if symbols_missing:
        for detail in missing_details:
            if detail["reason"] == "NO_DATA":
                print(f"    {detail['symbol']}: データ全体が存在しない")
            else:
                print(f"    {detail['symbol']}: {asof}が欠落 (最終日: {detail['latest_date']}, 行数: {detail['row_count']})")
    else:
        print("    (なし)")
    
    # 欠落銘柄の最終日付の統計
    if missing_details:
        latest_dates = [d["latest_date"] for d in missing_details if d["latest_date"] is not None]
        if latest_dates:
            print(f"\n【欠落銘柄の最終日付統計】")
            from collections import Counter
            date_counts = Counter(latest_dates)
            for date_str, count in sorted(date_counts.items(), reverse=True)[:5]:
                print(f"  {date_str}: {count}銘柄")
    
    return {
        "symbols_with_data": symbols_with_data,
        "symbols_missing": symbols_missing,
        "missing_details": missing_details
    }


def check_price_files(symbols: list, asof: str):
    """ローカルファイルの確認"""
    print("\n" + "=" * 60)
    print("=== ローカルファイル確認 ===")
    print("=" * 60)
    
    prices_dir = Path("data/raw/prices")
    if not prices_dir.exists():
        print(f"[WARNING] {prices_dir} が存在しません")
        return
    
    print(f"\n【確認ディレクトリ】")
    print(f"  {prices_dir}")
    
    # 各銘柄のファイルを確認
    files_found = []
    files_missing = []
    
    for symbol in symbols:
        # 複数のパターンを試す
        patterns = [
            f"{symbol}.parquet",
            f"{symbol}.csv",
            f"prices_{symbol}.parquet",
            f"prices_{symbol}.csv",
        ]
        
        found = False
        for pattern in patterns:
            file_path = prices_dir / pattern
            if file_path.exists():
                files_found.append((symbol, file_path))
                found = True
                break
        
        if not found:
            files_missing.append(symbol)
    
    print(f"\n【ファイル存在確認】")
    print(f"  ファイルあり: {len(files_found)}銘柄")
    print(f"  ファイルなし: {len(files_missing)}銘柄")
    
    if files_missing:
        print(f"\n  ファイルなしの銘柄: {sorted(files_missing)}")
    
    # ファイルありの銘柄で、12/29のデータがあるか確認
    if files_found:
        print(f"\n【ファイル内の日付確認（サンプル5件）】")
        for symbol, file_path in files_found[:5]:
            try:
                if file_path.suffix == ".parquet":
                    df = pd.read_parquet(file_path)
                else:
                    df = pd.read_csv(file_path)
                
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    latest_date = df["date"].max()
                    has_asof = (df["date"] == pd.to_datetime(asof)).any()
                    print(f"    {symbol}: 最新日={latest_date.strftime('%Y-%m-%d')}, {asof}={'あり' if has_asof else 'なし'}")
            except Exception as e:
                print(f"    {symbol}: 読み込みエラー - {e}")


def main():
    parser = argparse.ArgumentParser(description="prices欠落の根因特定")
    parser.add_argument("--asof", type=str, default="2025-12-29", help="確認対象日 (YYYY-MM-DD)")
    parser.add_argument("--universe", type=str, default=None, help="universeファイルパス (未指定ならlatest_universe.parquet)")
    
    args = parser.parse_args()
    
    # universeファイルのパス決定
    if args.universe:
        universe_path = Path(args.universe)
    else:
        # latest_universe.parquetを探す
        latest_uni = Path("data/intermediate/universe/latest_universe.parquet")
        if latest_uni.exists():
            universe_path = latest_uni
        else:
            # historyから該当日のファイルを探す
            asof_date = pd.to_datetime(args.asof)
            asof_str = asof_date.strftime("%Y%m%d")
            history_uni = Path(f"data/intermediate/universe/history/{asof_str}_universe.parquet")
            if history_uni.exists():
                universe_path = history_uni
            else:
                print(f"[ERROR] universeファイルが見つかりません")
                print(f"  確認したパス:")
                print(f"    {latest_uni}")
                print(f"    {history_uni}")
                return
    
    print("=" * 60)
    print("prices欠落 診断レポート")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象日: {args.asof}")
    print("=" * 60)
    
    # universe確認
    symbols = check_universe(universe_path, args.asof)
    if symbols is None:
        return
    
    # prices確認
    result = check_prices(symbols, args.asof)
    
    # ローカルファイル確認
    check_price_files(symbols, args.asof)
    
    print("\n" + "=" * 60)
    print("診断完了")
    print("=" * 60)
    
    # 要約
    print(f"\n【要約】")
    print(f"  universe銘柄数: {len(symbols)}")
    print(f"  {args.asof}のデータあり: {len(result['symbols_with_data'])}銘柄")
    print(f"  {args.asof}のデータなし: {len(result['symbols_missing'])}銘柄")
    
    if result['symbols_missing']:
        print(f"\n  [WARNING] {len(result['symbols_missing'])}銘柄で{args.asof}のデータが欠落しています")


if __name__ == "__main__":
    main()

