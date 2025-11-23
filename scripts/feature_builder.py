# scripts/feature_builder.py
# 3.1 銘柄スコアリング用のシンプルな特徴量生成 v0.1

import os
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_price_csv(ticker: str, prices_dir: Path) -> pd.DataFrame:
    """
    data/raw/prices/prices_{ticker}.csv を想定したローダー。
    date, open, high, low, close, adj_close, volume, turnover 形式。
    """
    path = prices_dir / ("prices_%s.csv" % ticker)
    if not path.exists():
        print("[feature_builder] price file not found, skip:", path)
        return pd.DataFrame()

    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError("price csv must have 'date' column: %s" % path)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ticker"] = ticker
    return df


def build_features_for_universe(
    tickers: List[str],
    asof: str,
    cfg: Dict,
) -> pd.DataFrame:
    """
    ユニバース銘柄について、3.1で必要な最低限の特徴量を返す。

    Returns
    -------
    df : pd.DataFrame
        index: MultiIndex(date, ticker)
        columns:
            ['close', 'volume',
             'ret_1', 'ret_5', 'ret_20',
             'ret_5_z', 'ret_20_z',
             'adv_20', 'vol_20',
             'strength', 'heat_flag']
    """
    prices_dir = PROJECT_ROOT / cfg["prices"]["dir"]

    lookback_short = int(cfg["features"]["lookback_short"])
    lookback_mid = int(cfg["features"]["lookback_mid"])
    adv_window = int(cfg["features"]["adv_window"])
    vol_window = int(cfg["features"]["vol_window"])
    heat_z_thresh = float(cfg["features"]["heat_z_thresh"])

    lookback = max(lookback_mid, adv_window, vol_window) + 5  # 余裕を持たせる

    frames = []
    for ticker in tickers:
        df = _load_price_csv(ticker, prices_dir)
        if df.empty:
            continue

        # asof 以前だけに制限
        if asof != "latest":
            cutoff = pd.to_datetime(asof)
            df = df[df["date"] <= cutoff]

        # 直近 lookback 行だけ残す
        if len(df) > lookback:
            df = df.iloc[-lookback:]

        frames.append(df)

    if not frames:
        raise RuntimeError("no price data loaded. check prices_dir and tickers.")

    px = pd.concat(frames, ignore_index=True)
    px = px.sort_values(["ticker", "date"]).reset_index(drop=True)

    # --- dtype 強制変換 ---
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px["open"] = pd.to_numeric(px["open"], errors="coerce")
    px["high"] = pd.to_numeric(px["high"], errors="coerce")
    px["low"] = pd.to_numeric(px["low"], errors="coerce")
    px["volume"] = pd.to_numeric(px["volume"], errors="coerce")
    if "turnover" in px.columns:
        px["turnover"] = pd.to_numeric(px["turnover"], errors="coerce")

    # NaN行を削除（closeがNaNの行を削除）
    px = px.dropna(subset=["close"])

    # 基本列
    px = px.set_index(["date", "ticker"])
    if "close" not in px.columns or "volume" not in px.columns:
        raise ValueError("price data must have 'close' and 'volume' columns.")

    # リターン
    px["ret_1"] = px.groupby("ticker")["close"].pct_change()
    px["ret_5"] = px.groupby("ticker")["close"].pct_change(5)
    px["ret_20"] = px.groupby("ticker")["close"].pct_change(20)

    # Zスコア（銘柄内）
    def _z(x: pd.Series) -> pd.Series:
        m = x.mean()
        s = x.std(ddof=1)
        return (x - m) / (s + 1e-8)

    px["ret_5_z"] = px.groupby("ticker")["ret_5"].transform(_z)
    px["ret_20_z"] = px.groupby("ticker")["ret_20"].transform(_z)

    # ADV, ボラ
    px["adv_20"] = (
        px.groupby("ticker")["volume"]
        .transform(lambda x: x.rolling(adv_window).mean())
    )

    px["vol_20"] = (
        px.groupby("ticker")["ret_1"]
        .transform(lambda x: x.rolling(vol_window).std())
    )

    # 強さ指標（単純に「銘柄ret_20 − 全銘柄平均ret_20」）
    mkt_ret_20 = px.groupby("date")["ret_20"].mean()
    px = px.reset_index().merge(
        mkt_ret_20.reset_index().rename(columns={"ret_20": "mkt_ret_20"}),
        on="date",
        how="left"
    ).set_index(["date", "ticker"])
    px["strength"] = px["ret_20"] - px["mkt_ret_20"]

    # 過熱フラグ
    px["heat_flag"] = (px["ret_5_z"].abs() > heat_z_thresh).astype(int)

    return px
