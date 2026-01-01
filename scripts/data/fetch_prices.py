# scripts/data/fetch_prices.py

import pandas as pd
import yfinance as yf
from pathlib import Path

INPUT_CSV = Path("data/raw/jpx_listings/20251031.csv")
OUTPUT_DIR = Path("data/raw/equities")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    df = pd.read_csv(INPUT_CSV)

    # ticker列が存在するか確認
    if "ticker" not in df.columns:
        raise KeyError("CSV に 'ticker' 列がありません")

    tickers = df["ticker"].dropna().unique()

    # 追加ティッカー（ETF/インバース）
    additional_tickers = [
        "1469.T",  # Japan Minimum Volatility ETF（最小分散）
        "1569.T",  # TOPIX Inverse（-1x）
        "1356.T",  # TOPIX Double Inverse（-2x）
    ]
    
    # 重複を避けて追加（ユニーク化）
    tickers = pd.Index(tickers).union(pd.Index(additional_tickers)).unique()
    tickers = sorted(tickers)  # ソートして一貫性を保つ

    print(f"取得対象銘柄数: {len(tickers)}")
    print("例:", tickers[:10])

    for tkr in tickers:
        print(f"\n=== Fetching {tkr} ===")

        try:
            data = yf.download(
                tkr,
                period="10y",
                interval="1d",
                auto_adjust=False,
                progress=False
            )
        except Exception as e:
            print(f"[ERROR] {tkr}: {e}")
            continue

        if data.empty:
            print(f"[EMPTY] No data for {tkr}")
            continue

        # parquet 形式に整理
        data = data.reset_index()
        
        # MultiIndexの列をフラット化（yf.download()がMultiIndexを返す場合がある）
        if isinstance(data.columns, pd.MultiIndex):
            # MultiIndexの場合は最初のレベルだけを使う
            data.columns = [col[0] if isinstance(col, tuple) and len(col) > 0 else str(col) for col in data.columns]
        
        # 列名の正規化（大文字小文字を考慮）
        rename_map = {}
        for col in data.columns:
            col_str = str(col).strip()
            if col_str.lower() in ("date", "datetime"):
                rename_map[col] = "date"
            elif col_str == "Open":
                rename_map[col] = "open"
            elif col_str == "High":
                rename_map[col] = "high"
            elif col_str == "Low":
                rename_map[col] = "low"
            elif col_str == "Close":
                rename_map[col] = "close"
            elif col_str in ("Adj Close", "AdjClose", "Adj_Close"):
                rename_map[col] = "adj_close"
            elif col_str == "Volume":
                rename_map[col] = "volume"
        
        if rename_map:
            data.rename(columns=rename_map, inplace=True)
        
        # デバッグ: 列名を確認
        if "close" not in data.columns or "volume" not in data.columns:
            print(f"[DEBUG] {tkr}: 列名確認 - columns={list(data.columns)}")

        data["symbol"] = tkr
        
        # turnover は必ず close * volume で計算
        if "close" in data.columns and "volume" in data.columns:
            try:
                # locを使って確実にSeriesを取得
                close_series = data.loc[:, "close"]
                volume_series = data.loc[:, "volume"]
                
                # 数値型に変換してから計算
                close_num = pd.to_numeric(close_series, errors="coerce")
                volume_num = pd.to_numeric(volume_series, errors="coerce")
                data["turnover"] = close_num * volume_num
            except Exception as e:
                print(f"[WARN] {tkr}: turnover計算エラー: {e}")
                print(f"  close列の型: {type(data.get('close'))}, volume列の型: {type(data.get('volume'))}")
                print(f"  列名: {list(data.columns)}")
                data["turnover"] = None
        else:
            print(f"[WARN] {tkr}: closeまたはvolume列が見つかりません。columns={list(data.columns)}")
            data["turnover"] = None

        # 必要な列だけに整理
        cols = ["date", "symbol", "open", "high", "low", "close", "adj_close", "volume", "turnover"]
        data = data[cols]

        # 保存
        out_path = OUTPUT_DIR / f"{tkr}.parquet"
        data.to_parquet(out_path, index=False)
        print(f"[OK] Saved → {out_path}")

    print("\n=== 完了：parquet生成しました ===")


if __name__ == "__main__":
    main()

