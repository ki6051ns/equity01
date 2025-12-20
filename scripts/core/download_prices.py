# scripts/download_prices.py
# ユニバース銘柄の株価を Yahoo Finance から一括ダウンロードして
# data/raw/prices/prices_{TICKER}.csv として保存するユーティリティ

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from tqdm import tqdm
except ImportError:  # tqdm が無ければダミー
    def tqdm(x, **kwargs):
        return x


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_universe_tickers(universe_path: Path) -> List[str]:
    if not universe_path.exists():
        raise FileNotFoundError(f"universe file not found: {universe_path}")
    df = pd.read_parquet(universe_path)
    if "ticker" not in df.columns:
        raise ValueError("universe parquet must have 'ticker' column.")
    tickers = df["ticker"].unique().tolist()
    return tickers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download daily prices for universe tickers via Yahoo Finance."
    )
    p.add_argument(
        "--universe",
        type=str,
        default="data/intermediate/universe/latest_universe.parquet",
        help="parquet file that contains 'ticker' column.",
    )
    p.add_argument(
        "--outdir",
        type=str,
        default="data/raw/prices",
        help="output directory for prices_{TICKER}.csv",
    )
    p.add_argument(
        "--start",
        type=str,
        default="2015-01-01",
        help="start date (YYYY-MM-DD)",
    )
    p.add_argument(
        "--end",
        type=str,
        default=None,
        help="end date (YYYY-MM-DD). default = today",
    )
    p.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="comma-separated tickers (override universe). e.g. 7203.T,9984.T",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="download at most N tickers (debug用)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="既存CSVがあっても上書きする",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="各ティッカー間のsleep秒数 (API制限対策)",
    )
    return p.parse_args()


def download_one(
    ticker: str,
    start: str,
    end: Optional[str],
) -> pd.DataFrame:
    """
    yfinance から1銘柄分の日足を取得し、
    equity01標準カラムに整形して返す。
    """
    end_ = end or date.today().isoformat()

    df = yf.download(
        ticker,
        start=start,
        end=end_,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df.empty:
        return df

    df = df.reset_index()

    # カラム名を統一
    rename_map = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename_map)

    # 必要な列だけに絞る
    cols = ["date", "open", "high", "low", "close", "adj_close", "volume"]
    df = df[cols]

    # 日付を ISO 文字列に
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # turnover（売買代金）= close * volume（ざっくり）
    df["turnover"] = df["close"] * df["volume"]

    return df


def main() -> None:
    args = parse_args()

    universe_path = (PROJECT_ROOT / args.universe).resolve()
    outdir = (PROJECT_ROOT / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = load_universe_tickers(universe_path)

    if args.limit is not None:
        tickers = tickers[: args.limit]

    print(f"[download_prices] universe file: {universe_path}")
    print(f"[download_prices] outdir       : {outdir}")
    print(f"[download_prices] tickers      : {len(tickers)} names")
    print(f"[download_prices] period       : {args.start} → {args.end or date.today().isoformat()}")

    for ticker in tqdm(tickers, desc="Downloading"):
        out_path = outdir / f"prices_{ticker}.csv"
        if out_path.exists() and not args.force:
            # 既にあるならスキップ
            continue

        try:
            df = download_one(ticker, start=args.start, end=args.end)
        except Exception as e:
            print(f"[download_prices] ERROR {ticker}: {e}")
            time.sleep(args.sleep)
            continue

        if df.empty:
            print(f"[download_prices] NO DATA for {ticker}")
            time.sleep(args.sleep)
            continue

        df.to_csv(out_path, index=False)
        time.sleep(args.sleep)

    print("[download_prices] done.")


if __name__ == "__main__":
    main()

