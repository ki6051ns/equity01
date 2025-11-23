#!/usr/bin/env python
from __future__ import annotations

import argparse, sys, os, json, math, logging, datetime as dt
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Optional, List, Dict


def setup_logger(logs_dir: str, asof: str):
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(logs_dir) / f"universe_builder_{asof}.log"
    logging.basicConfig(
        filename=log_path, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

def read_yaml(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def parse_args():
    ap = argparse.ArgumentParser(description="Build liquidity-top universe")
    ap.add_argument("--config", required=True)
    ap.add_argument("--asof", default=None)       # 例: 2025-09-30 / today
    ap.add_argument("--lookback", type=int, default=None)
    ap.add_argument("--top_ratio", type=float, default=None)
    return ap.parse_args()

def _resolve_asof(asof_opt: Optional[str]):
    if not asof_opt or asof_opt.lower()=="today":
        return dt.date.today().strftime("%Y-%m-%d")
    return asof_opt

def load_listings(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 期待カラム: ticker, market, type, name, sector 等
    req = {"ticker","market","type"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"listings missing columns: {missing}")
    return df

def load_prices_local(prices_dir: str, tickers: List[str], asof: str, lookback: int) -> Dict[str, pd.DataFrame]:
    from glob import glob
    out = {}
    end = pd.to_datetime(asof)
    # 余裕を持って読む（lookbackの20%増し）→整数に丸める
    pad = int(math.ceil(lookback * 1.2))
    start = end - pd.tseries.offsets.BDay(pad)
    for t in tickers:
        # 優先: {ticker}.parquet / {ticker}.csv
        p_parq = Path(prices_dir)/f"{t}.parquet"
        p_csv  = Path(prices_dir)/f"{t}.csv"

        df = None
        if p_parq.exists():
            df = pd.read_parquet(p_parq)
        elif p_csv.exists():
            df = pd.read_csv(p_csv)
        else:
            # フォールバック: prices_{ticker}.*
            g = glob(str(Path(prices_dir)/f"prices_{t}.*"))
            if g:
                p = Path(g[0])
                df = pd.read_parquet(p) if p.suffix==".parquet" else pd.read_csv(p)

        if df is None:
            continue
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"]<=end) & (df["date"]>=start)
        df = df.loc[mask, ["date","close","volume"]].dropna()
        # 返却直前: 型を整える
        df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")
        out[t] = df
    return out

def load_prices_yf(tickers: List[str], asof: str, lookback: int) -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    end = pd.to_datetime(asof) + pd.Timedelta(days=1)
    start = end - pd.tseries.offsets.BDay(int(math.ceil(lookback * 2)))
    out: Dict[str, pd.DataFrame] = {}

    for t in tickers:
        try:
            d = yf.download(
                t,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
            if d is None or len(d) == 0:
                continue

            # 列を正規化（Close/VolumeがDataFrameでもSeries化）
            # yfinanceは単一銘柄でも状況で列が階層化されることがある
            def _col(df, name):
                if name not in df.columns:
                    # MultiIndex対策：上位階層に name が含まれる場合を吸収
                    try:
                        tmp = df.xs(name, axis=1, level=-1, drop_level=False)
                        if tmp.shape[1] == 1:
                            s = tmp.iloc[:, 0]
                        else:
                            s = tmp.mean(axis=1)  # 複数列なら平均で潰す（稀ケース）
                        return s
                    except Exception:
                        return None
                v = df[name]
                # DataFrame→Series
                if isinstance(v, pd.DataFrame):
                    v = v.squeeze()
                return v

            close_raw = _col(d, "Close")
            vol_raw   = _col(d, "Volume")

            if close_raw is None or vol_raw is None:
                continue

            # インデックス→列（Date）
            d = pd.DataFrame({"date": d.index})
            d["close"]  = pd.to_numeric(pd.Series(close_raw).values, errors="coerce")
            d["volume"] = pd.to_numeric(pd.Series(vol_raw).values,  errors="coerce")

            # フィルタ
            d = d[["date", "close", "volume"]].dropna()
            if d.empty:
                continue

            out[t] = d

        except Exception as e:
            logging.warning(f"yfinance failed for {t}: {e}")

    return out

def compute_liquidity(df: pd.DataFrame, lookback: int) -> float:
    # DataFrameでなければ弾く
    if not isinstance(df, pd.DataFrame) or df.empty:
        return np.nan

    # 後ろN本のみ
    df = df.sort_values("date").tail(lookback)

    # 欠落カラムなら弾く
    if "close" not in df.columns or "volume" not in df.columns:
        return np.nan

    # どんな型でも数値化（Series以外が来てもOKにする）
    close_raw = df["close"]
    vol_raw   = df["volume"]

    # Series以外（ndarray/list/DataFrame等）はSeries化
    if not isinstance(close_raw, pd.Series):
        close_raw = pd.Series(close_raw)
    if not isinstance(vol_raw, pd.Series):
        vol_raw = pd.Series(vol_raw)

    close  = pd.to_numeric(close_raw, errors="coerce")
    volume = pd.to_numeric(vol_raw, errors="coerce")

    turn = close * volume  # 日次売買代金
    if turn.notna().sum() == 0:
        return np.nan

    return float(np.nanmean(turn.values))

def main():
    args = parse_args()
    cfg = read_yaml(args.config)
    asof = _resolve_asof(args.asof or cfg.get("asof"))
    lookback = args.lookback or cfg.get("lookback", 126)
    top_ratio = args.top_ratio or cfg.get("top_ratio", 0.20)

    setup_logger(cfg.get("logs_dir","logs"), asof)
    logging.info(f"Start universe build asof={asof} lookback={lookback} top_ratio={top_ratio}")

    listings = load_listings(cfg["inputs"]["listings_csv"])
    listings = listings[listings["market"].isin(cfg.get("markets",[]))]
    listings = listings[~listings["type"].isin(cfg.get("exclude_types",[]))]
    if cfg.get("exclude_tickers"):
        listings = listings[~listings["ticker"].isin(cfg["exclude_tickers"])]

    tickers = sorted(listings["ticker"].unique().tolist())
    logging.info(f"個別株銘柄数: {len(tickers)}銘柄")
    source = cfg["inputs"].get("source","auto").lower()

    prices = {}
    if source in ("local","auto"):
        prices.update(load_prices_local(cfg["inputs"]["prices_dir"], tickers, asof, lookback))
    if source in ("yfinance","auto"):
        # 足りない銘柄のみyfinanceで補完
        missing = [t for t in tickers if t not in prices]
        if missing:
            prices.update(load_prices_yf(missing, asof, lookback))

    recs=[]
    for t in tickers:
        df = prices.get(t)
        if df is None or len(df)<lookback//2:
            continue
        liq = compute_liquidity(df, lookback)
        if pd.notna(liq) and liq>0:
            recs.append({"ticker":t, "avg_turnover": liq})

    uni = pd.DataFrame(recs)
    if uni.empty:
        logging.error("No liquidity data computed. Aborting.")
        sys.exit(2)

    uni = uni.sort_values("avg_turnover", ascending=False).reset_index(drop=True)
    k = max(1, int(math.ceil(len(uni)*top_ratio)))
    # top_ratioに基づいて上位k銘柄のみを選択
    uni = uni.head(k).reset_index(drop=True)
    uni["liquidity_rank"] = np.arange(1, len(uni)+1)
    uni["asof"] = asof

    # 出力
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{asof.replace('-','')}_universe.parquet"
    uni.to_parquet(out_path, index=False)

    # latest シンボリック（Windowsで権限不可ならtry/except）
    if cfg["output"].get("write_latest_symlink", True):
        latest = out_dir / cfg["output"].get("latest_name","latest_universe.parquet")
        try:
            if latest.exists() or latest.is_symlink(): latest.unlink()
            latest.symlink_to(out_path.name)  # 相対symlink
        except Exception as e:
            logging.warning(f"symlink failed, fallback to copy: {e}")
            try:
                import shutil
                shutil.copy2(out_path, latest)
            except Exception as e2:
                logging.error(f"copy latest failed: {e2}")

    # 簡易サマリをSTDOUT
    head = uni.head(10).to_dict(orient="records")
    print(json.dumps({"asof": asof, "count_all": int(len(uni)),
                      "count_top": int(k),
                      "top10_preview": head}, ensure_ascii=False, indent=2))
    logging.info(f"Done. wrote {out_path}")
    sys.exit(0)

if __name__=="__main__":
    main()
