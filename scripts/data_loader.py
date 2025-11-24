"""
DataLoader: 日本株/為替/VIX/先物のローカル↔取得↔保存（安定版＋フォールバック強化）
- 既存CSV/Parquetがあれば読む／無ければ取得→保存
- yfinance には session を渡さない（0.2.66+ 仕様）
- 日本株は yfinance 失敗時に Stooq へ自動フォールバック（7203.T → 7203.jp）
- VIX は FRED → Stooq → yfinance の多段フォールバック
- 先物は NK=F 失敗時に ^N225 へフォールバック
- Stooq/FRED はHTTPリトライ＋certifiで安定化
- 空CSVはキャッシュ扱いしない
- offline_first=True でローカル優先（通信しない）

出力列: [date, open, high, low, close, adj_close, volume, turnover]
"""
from __future__ import annotations

import io
import time
import typing as t
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import certifi

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None

try:
    import requests  # type: ignore
except Exception:
    requests = None

DATE_COL = "date"
STD_COLS = [DATE_COL, "open", "high", "low", "close", "adj_close", "volume", "turnover"]


@dataclass
class SaveSpec:
    subdir: str
    stem: str  # ファイル名（拡張子除く）
    ext: str = "csv"


# -------------------- HTTP with retry -------------------- #
def _http_get_with_retry(url: str, headers=None, timeout: int = 20, tries: int = 3, backoff: float = 1.5):
    """小さめのHTTP GETリトライ（証明書はcertifi）"""
    if requests is None:
        raise RuntimeError("requests が利用できません。pip install requests を実行してください。")
    headers = headers or {"User-Agent": "Mozilla/5.0"}
    last_err = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, verify=certifi.where())
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            if i < tries - 1:
                time.sleep(backoff ** i)
    raise last_err


class DataLoader:
    def __init__(self, data_dir: str = "data/raw", tz: str = "Asia/Tokyo", offline_first: bool = False):
        self.data_dir = Path(data_dir)
        self.tz = tz
        self.offline_first = offline_first
        for sd in ("prices", "fx", "vix", "futures"):
            (self.data_dir / sd).mkdir(parents=True, exist_ok=True)

    # ========= 公開API ========= #
    def load_stock_data(self, symbol: str, *, refresh: bool = False) -> pd.DataFrame:
        sym = self._normalize_jp_symbol(symbol)
        spec = SaveSpec("prices", f"prices_{sym}")
        return self._read_or_fetch(spec, fetcher=lambda: self._fetch_stock_yf(sym), refresh=refresh)

    def load_volume_data(self, symbol: str, *, refresh: bool = False) -> pd.DataFrame:
        df = self.load_stock_data(symbol, refresh=refresh)
        return df[[DATE_COL, "volume"]].copy()

    def load_fx_data(self, pair: str = "USDJPY", *, refresh: bool = False) -> pd.DataFrame:
        pair = pair.upper()
        spec = SaveSpec("fx", f"fx_{pair}")
        return self._read_or_fetch(spec, fetcher=lambda: self._fetch_fx(pair), refresh=refresh)

    def load_vix_data(self, *, refresh: bool = False) -> pd.DataFrame:
        spec = SaveSpec("vix", "vix_VIXCLS")
        return self._read_or_fetch(spec, fetcher=self._fetch_vix_multi, refresh=refresh)

    def load_futures_data(self, contract: str = "NK=F", *, refresh: bool = False) -> pd.DataFrame:
        spec = SaveSpec("futures", f"futures_{contract}")
        def _fetch():
            try:
                return self._fetch_stock_yf(contract)
            except Exception:
                # 現物指数にフォールバック
                return self._fetch_stock_yf("^N225")
        return self._read_or_fetch(spec, fetcher=_fetch, refresh=refresh)

    # ========= 取得系 ========= #
    def _fetch_stock_yf(self, symbol: str) -> pd.DataFrame:
        if yf is None:
            raise RuntimeError("yfinance が利用できません。pip install yfinance を実行してください。")
        last_err = None
        for period in ("max", "1y"):
            try:
                df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
                if df is not None and not df.empty:
                    df = df.reset_index()
                    # インデックス列名の判定
                    dcols = [c for c in df.columns if str(c).lower() in ("date", "datetime") or "Date" in str(c)]
                    if dcols:
                        df.rename(columns={dcols[0]: DATE_COL}, inplace=True)
                    else:
                        df.rename(columns={df.columns[0]: DATE_COL}, inplace=True)
                    df.rename(columns={
                        "Open": "open",
                        "High": "high",
                        "Low": "low",
                        "Close": "close",
                        "Adj Close": "adj_close",
                        "Volume": "volume",
                    }, inplace=True)
                    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce").dt.tz_localize(None)
                    df[DATE_COL] = pd.to_datetime(df[DATE_COL].dt.date)
                    if "adj_close" not in df.columns:
                        df["adj_close"] = df.get("close")
                    if "volume" not in df.columns:
                        df["volume"] = pd.NA
                    df["turnover"] = (
                        pd.to_numeric(df.get("close"), errors="coerce")
                        * pd.to_numeric(df.get("volume"), errors="coerce")
                    ).astype("float64")
                    for c in STD_COLS:
                        if c not in df.columns:
                            df[c] = pd.NA
                    df = df[STD_COLS].dropna(subset=[DATE_COL]).sort_values(DATE_COL).reset_index(drop=True)
                    return df
            except Exception as e:
                last_err = e
        # yfinance で取れない場合は Stooq を試す（JP株のみ）
        try:
            return self._fetch_stock_stooq(symbol)
        except Exception:
            pass
        raise RuntimeError(f"yfinanceから取得できません（{symbol}）。ネットワーク/レート制限の可能性。詳細: {last_err}")

    def _fetch_stock_stooq(self, symbol: str) -> pd.DataFrame:
        """
        Stooq経由で日本株を取得。yfinance失敗時のフォールバック用。
        例: 7203.T -> 7203.jp / 7203 -> 7203.jp
        """
        if requests is None:
            raise RuntimeError("requests が利用できません。pip install requests を実行してください。")
        s = str(symbol).strip().upper()
        # JP株コードへ正規化
        if s.endswith(".T"):
            code = s[:-2]
        elif s.isdigit() and len(s) in (4, 5):
            code = s
        else:
            # それ以外はStooqで互換が薄いので回避
            raise RuntimeError(f"Stooq対応外のシンボル: {symbol}")
        stooq_sym = f"{code}.jp"
        url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
        r = _http_get_with_retry(url)
        df = pd.read_csv(io.StringIO(r.text))
        required = {"Date", "Open", "High", "Low", "Close"}
        if not required.issubset(df.columns):
            raise RuntimeError(f"Stooq列不一致: {df.columns}")
        df = df.rename(columns={
            "Date": DATE_COL,
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        df["adj_close"] = df["close"].astype("float32")
        df["turnover"] = pd.NA
        df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
        df = df[STD_COLS]
        df = self._normalize_df(df)
        if df.empty:
            raise RuntimeError("Stooq結果が空")
        return df

    def _fetch_fx(self, pair: str) -> pd.DataFrame:
        # 1) Stooq
        try:
            url = f"https://stooq.com/q/d/l/?s={pair.lower()}&i=d"
            r = _http_get_with_retry(url, headers={"User-Agent": "Mozilla/5.0"})
            df = pd.read_csv(io.StringIO(r.text))
            if not {"Date", "Open", "High", "Low", "Close"}.issubset(df.columns):
                raise ValueError("Unexpected columns from Stooq")
            df.rename(columns={"Date": DATE_COL, "Open": "open", "High": "high", "Low": "low", "Close": "close"}, inplace=True)
            df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
            df["adj_close"] = df["close"].astype("float32")
            df["volume"] = pd.NA
            df["turnover"] = pd.NA
            df = df[STD_COLS]
            df = self._normalize_df(df)
            return df
        except Exception:
            # 2) yfinance FX (=X)
            symbol = f"{pair}=X"
            return self._fetch_stock_yf(symbol)

    def _fetch_vix_multi(self) -> pd.DataFrame:
        errors = []
        # 1) FRED（2系統）
        fred_urls = [
            "https://fred.stlouisfed.org/series/VIXCLS/downloaddata/VIXCLS.csv",
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS",
        ]
        for url in fred_urls:
            try:
                r = _http_get_with_retry(url, headers={"User-Agent": "Mozilla/5.0"})
                df = pd.read_csv(io.StringIO(r.text))
                if "DATE" in df.columns and "VIXCLS" in df.columns:
                    df.rename(columns={"DATE": DATE_COL, "VIXCLS": "close"}, inplace=True)
                elif "DATE" in df.columns and "VALUE" in df.columns:
                    df.rename(columns={"DATE": DATE_COL, "VALUE": "close"}, inplace=True)
                else:
                    continue
                df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
                for c in ("open", "high", "low", "adj_close"):
                    df[c] = pd.to_numeric(df["close"], errors="coerce").astype("float32")
                df["volume"] = pd.NA
                df["turnover"] = pd.NA
                df = df[STD_COLS]
                df = self._normalize_df(df)
                return df
            except Exception as e:
                errors.append(f"FRED: {e}")
        # 2) Stooq (vix)
        try:
            url = "https://stooq.com/q/d/l/?s=vix&i=d"
            r = _http_get_with_retry(url, headers={"User-Agent": "Mozilla/5.0"})
            df = pd.read_csv(io.StringIO(r.text))
            df.rename(columns={"Date": DATE_COL, "Open": "open", "High": "high", "Low": "low", "Close": "close"}, inplace=True)
            df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
            df["adj_close"] = pd.to_numeric(df["close"], errors="coerce").astype("float32")
            df["volume"] = pd.NA
            df["turnover"] = pd.NA
            df = df[STD_COLS]
            df = self._normalize_df(df)
            return df
        except Exception as e:
            errors.append(f"Stooq: {e}")
        # 3) yfinance (^VIX)
        try:
            return self._fetch_stock_yf("^VIX")
        except Exception as e:
            errors.append(str(e))
            raise RuntimeError(f"VIX取得に失敗（FRED/Stooq/yf）: {errors}")

    # ========= IO共通 ========= #
    def _read_or_fetch(self, spec: SaveSpec, *, fetcher: t.Callable[[], pd.DataFrame], refresh: bool) -> pd.DataFrame:
        path_csv = self._path(spec, "csv")
        path_pq = self._path(spec, "parquet")

        def _is_valid_csv(p: Path) -> bool:
            if not p.exists():
                return False
            try:
                df = pd.read_csv(p, nrows=1)
                return not df.empty
            except Exception:
                return False

        # offline_first: ローカルがあれば通信しない
        if (not refresh) and self.offline_first and _is_valid_csv(path_csv):
            return self._read_csv(path_csv)
        if (not refresh) and _is_valid_csv(path_csv):
            return self._read_csv(path_csv)
        if (not refresh) and path_pq.exists():
            return self._read_parquet(path_pq)

        df = fetcher()
        if not isinstance(df, pd.DataFrame) or df.empty:
            raise RuntimeError(f"データ取得に失敗しました: {spec}")
        df = self._normalize_df(df)
        self._write_csv(df, path_csv)
        return df

    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        # date列名の確保
        if DATE_COL not in df.columns:
            for c in df.columns:
                if str(c).lower() in ("date", "datetime"):
                    df = df.rename(columns={c: DATE_COL})
                    break
        df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce").dt.tz_localize(None)
        df[DATE_COL] = pd.to_datetime(df[DATE_COL].dt.date)
        for c in ("open", "high", "low", "close", "adj_close", "turnover"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("float64")
        # 列を揃える
        for c in STD_COLS:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[STD_COLS].dropna(subset=[DATE_COL]).drop_duplicates(subset=[DATE_COL]).sort_values(DATE_COL)
        return df.reset_index(drop=True)

    def _path(self, spec: SaveSpec, ext: str) -> Path:
        return self.data_dir / spec.subdir / f"{spec.stem}.{ext}"

    def _write_csv(self, df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)

    def _read_csv(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        if DATE_COL in df.columns:
            df[DATE_COL] = pd.to_datetime(df[DATE_COL])
        return df

    def _read_parquet(self, path: Path) -> pd.DataFrame:
        df = pd.read_parquet(path)
        if DATE_COL in df.columns:
            df[DATE_COL] = pd.to_datetime(df[DATE_COL])
        return df

    @staticmethod
    def _normalize_jp_symbol(symbol: str) -> str:
        s = str(symbol).strip()
        if s.endswith(".T"):
            return s
        if s.isdigit() and len(s) in (4, 5):
            return f"{s}.T"
        return s


def load_prices() -> pd.DataFrame:
    """
    build_features から呼ばれる用。
    必ず columns に
    ['date', 'open', 'high', 'low', 'close', 'adj_close', 'volume', 'turnover']
    のどれか一部 or 全部を含む DataFrame を返す。
    """
    # DataLoader を使って価格データを取得
    dl = DataLoader(data_dir="data/raw", tz="Asia/Tokyo")
    
    # 例：7203.T（トヨタ）のデータを取得
    # 複数銘柄対応時は、ここでループして結合する
    try:
        df = dl.load_stock_data("7203.T")
    except Exception as e:
        # 取得に失敗した場合は、保存済みのCSV/Parquetを読み込む
        csv_path = Path("data/raw/prices/prices_7203.T.csv")
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df[DATE_COL] = pd.to_datetime(df[DATE_COL])
        else:
            raise RuntimeError(f"価格データの取得に失敗しました: {e}")
    
    # デバッグ用：今何が返っているか確認
    print("load_prices() columns:", df.columns.tolist())
    print(df.head())
    
    return df


def main():
    dl = DataLoader(data_dir="data/raw", tz="Asia/Tokyo")
    # 例1：株価
    try:
        print("prices:")
        print(dl.load_stock_data("7203.T").tail(3))
    except Exception as e:
        print("[WARN] stock fetch failed:", e)
    # 例2：FX
    try:
        print("fx:")
        print(dl.load_fx_data("USDJPY").tail(3))
    except Exception as e:
        print("[WARN] fx fetch failed:", e)
    # 例3：VIX
    try:
        print("vix:")
        print(dl.load_vix_data().tail(3))
    except Exception as e:
        print("[WARN] vix fetch failed:", e)
    # 例4：先物
    try:
        print("futures:")
        print(dl.load_futures_data("NK=F").tail(3))
    except Exception as e:
        print("[WARN] futures fetch failed:", e)


if __name__ == "__main__":
    main()
