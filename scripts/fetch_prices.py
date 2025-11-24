# scripts/fetch_prices.py

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
        data.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume"
        }, inplace=True)

        data["symbol"] = tkr
        data["turnover"] = None  # 必須ではないので空でOK

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

