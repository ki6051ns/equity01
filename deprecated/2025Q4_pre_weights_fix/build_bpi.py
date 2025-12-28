#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
build_bpi.py

1569.T（TOPIXインバース -1x）と 1356.T（TOPIXダブルインバース -2x）
から Bear Pressure Index (BPI) を構築して data/processed/bpi.parquet に保存する。
"""

from pathlib import Path
import pandas as pd


# ========= 設定 =========
DATA_DIR = Path("data/raw/equities")    # 価格 parquet の置き場所（fetch_prices.pyの出力先に合わせる）
OUT_PATH = Path("data/processed/bpi.parquet")

TICKERS = ["1569.T", "1356.T"]
DATE_COL = "date"
PRICE_COL = "adj_close"                 # リターン計算に使う列


def load_price(ticker: str) -> pd.DataFrame:
    """
    単一ティッカー用 parquet を読み込み、
    date を datetime にしてソートして返す。
    """
    path = DATA_DIR / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"price file not found for {ticker}: {path}")

    df = pd.read_parquet(path)
    if DATE_COL not in df.columns:
        raise ValueError(f"{ticker}: column '{DATE_COL}' not found")

    df = df.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    df = df.sort_values(DATE_COL)

    if PRICE_COL not in df.columns:
        raise ValueError(f"{ticker}: column '{PRICE_COL}' not found")

    # 必要な列だけ残す
    df = df[[DATE_COL, PRICE_COL]].rename(columns={PRICE_COL: f"{ticker}_price"})
    return df


def compute_daily_return(df: pd.DataFrame, price_col: str) -> pd.Series:
    """
    日次リターン（単純リターン）を計算。
    r_t = price_t / price_{t-1} - 1
    """
    ret = df[price_col].pct_change()
    return ret


def build_bpi() -> pd.DataFrame:
    # --- 価格読み込み ---
    df_1569 = load_price("1569.T")
    df_1356 = load_price("1356.T")

    # --- 日付で内部結合 ---
    df = pd.merge(df_1569, df_1356, on=DATE_COL, how="inner")

    # --- 日次リターン計算 ---
    df["r_1569"] = compute_daily_return(df, "1569.T_price")
    df["r_1356"] = compute_daily_return(df, "1356.T_price")

    # 最初の NaN 行は後でまとめて落とす
    # --- BPI 生値（非線形） ---
    # rolling sum を使用
    # 過去N日間のリターンの合計（60営業日）
    window = 120
    r_1569_sum = df["r_1569"].rolling(window=window, min_periods=1).sum()
    r_1356_sum = df["r_1356"].rolling(window=window, min_periods=1).sum()
    
    one_plus_1569 = 1.0 + r_1569_sum
    one_plus_1356 = 1.0 + r_1356_sum

    df["bpi_raw"] = (one_plus_1569.pow(2) + one_plus_1356.pow(2)) / 2.0 - 1.0

    # --- 0フロア（下限0） ---
    df["bpi"] = df["bpi_raw"].clip(lower=0.0)

    # --- スムーズなバージョンも作っておく ---
    # 21営業日 ≒ 1ヶ月, 63営業日 ≒ 3ヶ月
    df["bpi_21d"] = df["bpi"].rolling(window=21, min_periods=10).mean()
    df["bpi_63d"] = df["bpi"].rolling(window=63, min_periods=21).mean()

    # 最初のNaNを落としておく（リターン計算起因）
    df = df.dropna(subset=["bpi"]).reset_index(drop=True)

    # 最低限残したい列だけ
    out = df[[DATE_COL, "bpi_raw", "bpi", "bpi_21d", "bpi_63d"]].copy()

    return out


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpi = build_bpi()
    bpi.to_parquet(OUT_PATH, index=False)
    print("BPI saved to:", OUT_PATH)
    print(bpi.tail())


if __name__ == "__main__":
    main()
