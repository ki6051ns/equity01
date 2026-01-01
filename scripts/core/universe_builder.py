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

def load_prices_yf(tickers: List[str], asof: str, lookback: int, prices_dir: str = "data/raw/prices") -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    end = pd.to_datetime(asof) + pd.Timedelta(days=1)
    # 最適化: lookbackの2倍ではなく、1.2倍程度に短縮（必要な期間のみ取得）
    start = end - pd.tseries.offsets.BDay(int(math.ceil(lookback * 1.2)))
    out: Dict[str, pd.DataFrame] = {}

    # 最適化: バッチ取得を試行（yfinanceは複数銘柄を一度に取得できる場合がある）
    if len(tickers) > 10:
        try:
            # バッチ取得を試行（失敗したら個別取得にフォールバック）
            batch_data = yf.download(
                tickers,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,  # 並列化を有効化
            )
            if batch_data is not None and len(batch_data) > 0:
                # バッチ取得が成功した場合の処理
                for t in tickers:
                    try:
                        close_col = None
                        vol_col = None
                        if isinstance(batch_data.columns, pd.MultiIndex):
                            # MultiIndexの場合
                            if (t, "Close") in batch_data.columns:
                                close_col = (t, "Close")
                            if (t, "Volume") in batch_data.columns:
                                vol_col = (t, "Volume")
                        else:
                            # 単一銘柄の場合
                            if "Close" in batch_data.columns:
                                close_col = "Close"
                            if "Volume" in batch_data.columns:
                                vol_col = "Volume"
                        
                        if close_col is not None and vol_col is not None:
                            d = pd.DataFrame({"date": batch_data.index})
                            d["close"] = pd.to_numeric(batch_data[close_col].values, errors="coerce")
                            d["volume"] = pd.to_numeric(batch_data[vol_col].values, errors="coerce")
                            d = d[["date", "close", "volume"]].dropna()
                            if not d.empty:
                                out[t] = d
                    except Exception:
                        pass
                
                # バッチ取得で取得できた銘柄は個別取得をスキップ
                remaining = [t for t in tickers if t not in out]
                if not remaining:
                    return out
                tickers = remaining
        except Exception as e:
            logging.warning(f"Batch download failed, falling back to individual downloads: {e}")

    # 個別取得（バッチ取得が失敗した場合、または残りの銘柄）
    for t in tickers:
        try:
            d = yf.download(
                t,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,  # レート制限対策
            )
            if d is None or len(d) == 0:
                # yfinance失敗時はローカル価格で補完を試行
                logging.warning(f"yfinance returned empty for {t}, trying local prices")
                local_prices = load_prices_local(prices_dir, [t], asof, lookback)
                if t in local_prices and not local_prices[t].empty:
                    # 前回終値を最新日として使用（当日欠損を埋める）
                    df_local = local_prices[t].copy()
                    last_close = df_local["close"].iloc[-1] if len(df_local) > 0 else None
                    if last_close is not None:
                        # 最新日として当日のデータを作成（前回終値を保持）
                        latest_date = pd.to_datetime(asof)
                        d_fallback = pd.DataFrame({
                            "date": [latest_date],
                            "close": [last_close],
                            "volume": [0.0],  # 当日はvolume不明
                        })
                        out[t] = d_fallback
                        logging.info(f"Using local last close for {t}: {last_close:.2f}")
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
                # yfinance失敗時はローカル価格で補完を試行
                logging.warning(f"yfinance missing Close/Volume for {t}, trying local prices")
                local_prices = load_prices_local(prices_dir, [t], asof, lookback)
                if t in local_prices and not local_prices[t].empty:
                    df_local = local_prices[t].copy()
                    last_close = df_local["close"].iloc[-1] if len(df_local) > 0 else None
                    if last_close is not None:
                        latest_date = pd.to_datetime(asof)
                        d_fallback = pd.DataFrame({
                            "date": [latest_date],
                            "close": [last_close],
                            "volume": [0.0],
                        })
                        out[t] = d_fallback
                        logging.info(f"Using local last close for {t}: {last_close:.2f}")
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
    import time
    start_time = time.time()
    
    args = parse_args()
    cfg = read_yaml(args.config)
    asof = _resolve_asof(args.asof or cfg.get("asof"))
    lookback = args.lookback or cfg.get("lookback", 126)
    top_ratio = args.top_ratio or cfg.get("top_ratio", 0.20)

    setup_logger(cfg.get("logs_dir","logs"), asof)
    logging.info(f"Start universe build asof={asof} lookback={lookback} top_ratio={top_ratio}")

    # 計測: JPX listings読み込み
    step_start = time.time()
    listings = load_listings(cfg["inputs"]["listings_csv"])
    logging.info(f"[TIMING] load_listings: {time.time() - step_start:.2f}秒")
    listings = listings[listings["market"].isin(cfg.get("markets",[]))]
    listings = listings[~listings["type"].isin(cfg.get("exclude_types",[]))]
    if cfg.get("exclude_tickers"):
        listings = listings[~listings["ticker"].isin(cfg["exclude_tickers"])]

    # 計測: フィルタ処理
    step_start = time.time()
    tickers = sorted(listings["ticker"].unique().tolist())
    logging.info(f"個別株銘柄数: {len(tickers)}銘柄")
    logging.info(f"[TIMING] filter_listings: {time.time() - step_start:.2f}秒")
    
    source = cfg["inputs"].get("source","auto").lower()

    # 計測: 価格データ読み込み
    step_start = time.time()
    prices = {}
    if source in ("local","auto"):
        prices.update(load_prices_local(cfg["inputs"]["prices_dir"], tickers, asof, lookback))
        logging.info(f"[TIMING] load_prices_local: {time.time() - step_start:.2f}秒 (取得銘柄数: {len(prices)})")
    if source in ("yfinance","auto"):
        # 足りない銘柄のみyfinanceで補完
        missing = [t for t in tickers if t not in prices]
        if missing:
            yf_start = time.time()
            try:
                # prices_dirを渡す（ローカル補完用）
                prices.update(load_prices_yf(missing, asof, lookback))
                yf_obtained = len([t for t in missing if t in prices])
                logging.info(f"[TIMING] load_prices_yf: {time.time() - yf_start:.2f}秒 (取得銘柄数: {yf_obtained})")
            except Exception as e:
                # 【運用安定化】yfinance取得失敗時の挙動
                # A案（堅牢）: 前回のlatest_universeを使って継続
                # B案（品質）: ExitCode!=0で止める（その日は運用しない）
                # 現在はA案を採用（運用継続性を優先）
                logging.error(f"[ERROR] yfinance取得失敗: {e}")
                logging.error(f"[ERROR] 前回のlatest_universeを使用して継続します")
                
                # 前回のlatest_universeを読み込む
                out_dir = Path(cfg["output"]["dir"])
                latest_path = out_dir / cfg["output"].get("latest_name", "latest_universe.parquet")
                if latest_path.exists():
                    try:
                        latest_uni = pd.read_parquet(latest_path)
                        logging.info(f"[FALLBACK] 前回のuniverseを使用: {len(latest_uni)}銘柄 (asof: {latest_uni['asof'].iloc[0] if 'asof' in latest_uni.columns and len(latest_uni) > 0 else 'N/A'})")
                        # 前回のuniverseをそのまま出力（日付は更新しない）
                        latest_uni["asof"] = asof  # 日付のみ更新
                        out_dir.mkdir(parents=True, exist_ok=True)
                        history_dir = out_dir / "history"
                        history_dir.mkdir(parents=True, exist_ok=True)
                        out_path = history_dir / f"{asof.replace('-','')}_universe.parquet"
                        latest_uni.to_parquet(out_path, index=False, compression="snappy")
                        
                        # latestを更新
                        if cfg["output"].get("write_latest_symlink", True):
                            latest = out_dir / cfg["output"].get("latest_name", "latest_universe.parquet")
                            try:
                                if latest.exists() or latest.is_symlink(): latest.unlink()
                                # Windowsではhardlinkを試す
                                if os.name == "nt":  # Windows
                                    try:
                                        os.link(out_path, latest)
                                    except (OSError, AttributeError):
                                        latest.symlink_to(out_path.name)
                                else:
                                    latest.symlink_to(out_path.name)
                            except Exception:
                                import shutil
                                shutil.copy2(out_path, latest)
                        
                        # 簡易サマリをSTDOUT
                        head = latest_uni.head(10).to_dict(orient="records")
                        print(json.dumps({"asof": asof, "count_all": int(len(latest_uni)),
                                          "count_top": int(len(latest_uni)),
                                          "top10_preview": head, "fallback": True}, ensure_ascii=False, indent=2))
                        
                        total_time = time.time() - start_time
                        logging.info(f"Done (fallback). wrote {out_path}")
                        logging.info(f"[TIMING] TOTAL: {total_time:.2f}秒 ({total_time/60:.1f}分)")
                        sys.exit(0)
                    except Exception as e2:
                        logging.error(f"[ERROR] 前回のuniverse読み込みも失敗: {e2}")
                        logging.error("[ERROR] 運用を継続できません。手動対応が必要です。")
                        sys.exit(2)
                else:
                    logging.error("[ERROR] 前回のuniverseファイルが見つかりません。運用を継続できません。")
                    sys.exit(2)

    # 計測: 流動性計算・ランキング
    step_start = time.time()
    recs=[]
    for t in tickers:
        df = prices.get(t)
        if df is None or len(df)<lookback//2:
            # 欠損銘柄はrank計算から除外（選定に混ぜない）
            logging.debug(f"Skipping {t}: insufficient price data (len={len(df) if df is not None else 0})")
            continue
        liq = compute_liquidity(df, lookback)
        if pd.notna(liq) and liq>0:
            recs.append({"ticker":t, "avg_turnover": liq})
        else:
            # 流動性が計算できない銘柄も除外
            logging.debug(f"Skipping {t}: liquidity={liq}")

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
    logging.info(f"[TIMING] compute_liquidity_and_rank: {time.time() - step_start:.2f}秒 (対象銘柄数: {len(recs)}, 選定銘柄数: {len(uni)})")

    # 計測: ファイル出力
    step_start = time.time()
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 日付付きuniverseファイルはhistory/に保存（誤爆防止）
    history_dir = out_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    out_path = history_dir / f"{asof.replace('-','')}_universe.parquet"
    uni.to_parquet(out_path, index=False, compression="snappy")
    logging.info(f"[TIMING] write_parquet: {time.time() - step_start:.2f}秒")

    # latest シンボリック（Windowsで権限不可ならhardlink→copy）
    if cfg["output"].get("write_latest_symlink", True):
        latest = out_dir / cfg["output"].get("latest_name","latest_universe.parquet")
        try:
            if latest.exists() or latest.is_symlink(): latest.unlink()
            # Windowsではhardlinkを試す（symlinkより権限問題が出にくい）
            if os.name == "nt":  # Windows
                try:
                    # 同一ドライブならhardlinkを試す
                    os.link(out_path, latest)
                except (OSError, AttributeError):
                    # hardlink失敗時はsymlinkを試す
                    latest.symlink_to(out_path.name)  # 相対symlink
            else:
                latest.symlink_to(out_path.name)  # 相対symlink
        except Exception as e:
            logging.warning(f"symlink/hardlink failed, fallback to copy: {e}")
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
    
    total_time = time.time() - start_time
    logging.info(f"Done. wrote {out_path}")
    logging.info(f"[TIMING] TOTAL: {total_time:.2f}秒 ({total_time/60:.1f}分)")
    sys.exit(0)

if __name__=="__main__":
    main()
