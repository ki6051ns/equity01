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


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # scripts/core/download_prices.py -> scripts -> equity01


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
    retry_max: int = 3,
    retry_backoff: float = 2.0,
) -> pd.DataFrame:
    """
    yfinance から1銘柄分の日足を取得し、
    equity01標準カラムに整形して返す。
    
    Args:
        ticker: ティッカーシンボル
        start: 開始日 (YYYY-MM-DD)
        end: 終了日 (YYYY-MM-DD, Noneなら今日)
        retry_max: リトライ最大回数
        retry_backoff: リトライ時のバックオフ秒数（指数バックオフ）
    """
    # yfinanceのendはexclusive（指定日を含まない）なので、1日後を指定
    if end:
        end_date = pd.to_datetime(end)
        end_ = (end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        end_ = (date.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    
    last_err = None
    for attempt in range(retry_max):
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end_,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,  # レート制限対策
            )
            break  # 成功したらループを抜ける
        except Exception as e:
            last_err = e
            if attempt < retry_max - 1:
                sleep_sec = retry_backoff ** attempt
                time.sleep(sleep_sec)
            else:
                # 最終試行でも失敗した場合は例外を再発生
                raise last_err

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

    # 集計用の変数
    requested_symbols = len(tickers)
    fetched_symbols = 0
    written_files = 0
    failed_symbols = []
    empty_symbols = []
    symbols_missing_asof = []
    processed_count = 0
    
    asof_date = pd.to_datetime(args.end or date.today().isoformat())

    # 【⑤ 祝日・価格未更新日の挙動】
    # - 取得不能時は例外をキャッチして警告を出力し、次の銘柄に進む（処理は継続）
    # - 営業日カレンダーによる事前判定は行わない（Yahoo Finance側のデータ有無に依存）
    # - 営業日カレンダー実装は不要（予防線のみ）
    for ticker in tqdm(tickers, desc="Downloading"):
        processed_count += 1
        out_path = outdir / f"prices_{ticker}.csv"
        
        # 既存ファイルの確認
        file_exists = out_path.exists()
        last_date = None
        need_fetch = False
        
        if file_exists and not args.force:
            # 既存ファイルがある場合、asof日付の確認
            try:
                existing_df = pd.read_csv(out_path)
                existing_df["date"] = pd.to_datetime(existing_df["date"])
                last_date = existing_df["date"].max()
                has_asof = (existing_df["date"] == asof_date).any()
                
                # asof日付が欠落している場合は強制fetch
                need_fetch = (last_date is None) or (last_date < asof_date)
                
                if not has_asof:
                    symbols_missing_asof.append(ticker)
            except Exception as e:
                # 既存ファイルの読み込みに失敗した場合はfetch
                need_fetch = True
                print(f"[download_prices] WARNING {ticker}: 既存ファイル読み込みエラー、再取得します: {e}")
        else:
            # ファイルが存在しない、またはforce指定の場合はfetch
            need_fetch = True
        
        # デバッグログ（最初の3銘柄のみ）
        if processed_count <= 3:
            print(f"[download_prices] PROCESS ticker={ticker} file_exists={file_exists} last_date={last_date} end_date={asof_date.strftime('%Y-%m-%d')} need_fetch={need_fetch}")
        
        # need_fetch=Falseの場合はスキップ
        if not need_fetch:
            continue
        
        # fetch実行
        if processed_count <= 3:
            print(f"[download_prices] FETCH_START ticker={ticker}")
        
        try:
            df = download_one(ticker, start=args.start, end=args.end, retry_max=3, retry_backoff=2.0)
            fetched_symbols += 1
        except Exception as e:
            print(f"[download_prices] ERROR {ticker}: {e}")
            failed_symbols.append(ticker)
            time.sleep(args.sleep)
            continue

        if df.empty:
            print(f"[download_prices] NO DATA for {ticker}")
            empty_symbols.append(ticker)
            time.sleep(args.sleep)
            continue

        # asof日付の確認
        df["date"] = pd.to_datetime(df["date"])
        has_asof = (df["date"] == asof_date).any()
        max_date = df["date"].max()
        
        if processed_count <= 3:
            print(f"[download_prices] FETCH_DONE ticker={ticker} rows={len(df)} max_date={max_date.strftime('%Y-%m-%d')}")
        
        if not has_asof:
            symbols_missing_asof.append(ticker)
            print(f"[download_prices] WARNING {ticker}: {asof_date.strftime('%Y-%m-%d')} not found (latest: {max_date.strftime('%Y-%m-%d')})")

        try:
            df.to_csv(out_path, index=False)
            written_files += 1
        except Exception as e:
            print(f"[download_prices] WRITE ERROR {ticker}: {e}")
            failed_symbols.append(ticker)
            time.sleep(args.sleep)
            continue

        time.sleep(args.sleep)

    # 集計ログを出力
    print("\n[download_prices] ===== 集計 =====")
    print(f"[download_prices] requested_symbols = {requested_symbols}")
    print(f"[download_prices] processed_count = {processed_count}")
    print(f"[download_prices] fetched_symbols = {fetched_symbols}")
    print(f"[download_prices] written_files = {written_files}")
    print(f"[download_prices] failed_symbols = {len(failed_symbols)}")
    if failed_symbols:
        print(f"[download_prices]   → {failed_symbols}")
    print(f"[download_prices] empty_symbols = {len(empty_symbols)}")
    if empty_symbols:
        print(f"[download_prices]   → {empty_symbols}")
    print(f"[download_prices] symbols_missing_asof ({asof_date.strftime('%Y-%m-%d')}) = {len(symbols_missing_asof)}")
    if symbols_missing_asof:
        print(f"[download_prices]   → {symbols_missing_asof}")
    
    # 異常検知
    if processed_count == 0:
        raise RuntimeError("processed_count == 0: ループが一度も実行されていません")
    
    if requested_symbols > 0 and fetched_symbols == 0 and len(symbols_missing_asof) == requested_symbols:
        print(f"\n[download_prices] ERROR: 全銘柄でasof日付が欠落しているのに、fetchが実行されていません")
        print(f"[download_prices]   これは異常です。need_fetch判定のロジックを確認してください。")
    
    print("[download_prices] done.")


if __name__ == "__main__":
    main()

