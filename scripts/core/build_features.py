# scripts/build_features.py

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from pathlib import Path as PathLib

# scripts ディレクトリをパスに追加
# build_features.py は scripts/core/ にあるため、scripts/ をパスに追加
SCRIPT_DIR = PathLib(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
# プロジェクトルートもパスに追加（scripts.core をインポートするため）
PROJECT_ROOT = PathLib(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.lib.feature_builder import FeatureBuilderConfig, build_feature_matrix
from scripts.core.scoring_engine import compute_scores_all, _zscore
# 【② run_scoring 二重実行の可視化】
# build_features.py 内で compute_scores_all を呼び出しているため、
# run_scoring.py を別途実行する場合は二重実行となる可能性がある
# 実行フローは変更しない（現状のまま）
from tools.lib import data_loader


def main():
    prices = data_loader.load_prices()
    
    # 【修正】universeに含まれる銘柄のみをフィルタリング（1306.TなどのETF混入防止）
    universe_path = Path("data/intermediate/universe/latest_universe.parquet")
    if universe_path.exists():
        df_universe = pd.read_parquet(universe_path)
        if "ticker" in df_universe.columns:
            universe_tickers = set(df_universe["ticker"].unique())
            prices_before = len(prices)
            prices = prices[prices["symbol"].isin(universe_tickers)].copy()
            prices_after = len(prices)
            excluded = prices_before - prices_after
            if excluded > 0:
                excluded_symbols = set(prices["symbol"].unique()) - universe_tickers if "symbol" in prices.columns else set()
                print(f"[INFO] Universeフィルタリング: {excluded} rows excluded")
                if excluded_symbols:
                    print(f"[INFO] 除外されたsymbol: {sorted(excluded_symbols)}")
        else:
            print(f"[WARN] Universeファイルに'ticker'列がありません。フィルタリングをスキップします。")
    else:
        print(f"[WARN] Universeファイルが見つかりません: {universe_path}。フィルタリングをスキップします。")

    # ---------- カラム補正 ----------
    # date
    if "date" not in prices.columns:
        raise KeyError(f"'date' 列が必要です: {prices.columns.tolist()}")

    # symbol（無ければ単一銘柄とみなす）
    if "symbol" not in prices.columns:
        prices = prices.copy()
        prices["symbol"] = "SINGLE"

    # close
    if "close" not in prices.columns:
        for cand in ["adj_close", "Adj Close", "Adj_Close", "ADJ_CLOSE"]:
            if cand in prices.columns:
                prices = prices.rename(columns={cand: "close"})
                break

    if "close" not in prices.columns:
        raise KeyError(f"'close' 列が必要です: {prices.columns.tolist()}")

    # turnover は毎回作り直す
    if "volume" not in prices.columns:
        raise KeyError(f"'volume' 列が必要です: {prices.columns.tolist()}")

    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["symbol", "date"])

    # ---------- リターン ----------
    prices["ret_1d"] = prices.groupby("symbol")["close"].pct_change()
    prices["ret_5d"] = prices.groupby("symbol")["close"].pct_change(5)
    prices["ret_20d"] = prices.groupby("symbol")["close"].pct_change(20)

    # ---------- ボラ ----------
    prices["vol_20d"] = (
        prices.groupby("symbol")["ret_1d"]
        .transform(lambda x: x.rolling(window=20, min_periods=5).std())
    )

    # ---------- ADV ----------
    prices["turnover"] = prices["close"] * prices["volume"]
    prices["adv_20d"] = (
        prices.groupby("symbol")["turnover"]
        .transform(lambda x: x.rolling(window=20, min_periods=5).mean())
    )

    # ---------- TOPIX データの読み込みとマージ ----------
    # 【① TOPIX依存】TOPIX（日次指数リターン）を参照
    # - データ欠損時は mkt_ret_1d = 0.0 でフォールバック（警告を出力）
    # - 無言スルー禁止：データが見つからない場合は警告を出力
    tpx_path = Path("data/processed/index_tpx_daily.parquet")
    if tpx_path.exists():
        df_tpx = pd.read_parquet(tpx_path)
        df_tpx = df_tpx.sort_values("trade_date").reset_index(drop=True)
        df_tpx["date"] = pd.to_datetime(df_tpx["trade_date"])
        # TOPIXの日次リターンを計算
        df_tpx["mkt_ret_1d"] = df_tpx["tpx_ret_cc"]
        # prices にマージ
        prices = prices.merge(
            df_tpx[["date", "mkt_ret_1d"]],
            on="date",
            how="left"
        )
    else:
        print("警告: TOPIXデータが見つかりません。mkt_ret_1d は使用できません。")
        prices["mkt_ret_1d"] = 0.0

    # ---------- Variant E/F/G 用の特徴量 ----------
    # downside_ret_1d: 下落した日のみのリターン
    prices["downside_ret_1d"] = prices["ret_1d"].where(prices["ret_1d"] < 0, 0.0)
    
    # downside_vol_60d: 下落日のボラティリティ（60日ローリング）
    prices["downside_vol_60d"] = (
        prices.groupby("symbol")["downside_ret_1d"]
        .transform(lambda x: x.rolling(window=60, min_periods=20).std())
    )
    
    # down_beta_252d: 下落相場でのベータ（252日ローリング）
    def rolling_downside_beta(r, m, window=252, min_periods=60):
        """
        下落相場（m < 0）のみを使ってベータを計算
        """
        out = []
        for i in range(len(r)):
            start = max(0, i - window + 1)
            r_win = r.iloc[start:i+1]
            m_win = m.iloc[start:i+1]
            mask = m_win < 0
            r_d = r_win[mask]
            m_d = m_win[mask]
            if len(r_d) < min_periods:
                out.append(np.nan)
            else:
                cov = np.cov(r_d, m_d)[0, 1]
                var = np.var(m_d)
                out.append(cov / var if var > 0 else np.nan)
        return pd.Series(out, index=r.index)
    
    # 各銘柄ごとにdownside betaを計算
    prices["down_beta_252d"] = np.nan
    for symbol in prices["symbol"].unique():
        mask = prices["symbol"] == symbol
        r = prices.loc[mask, "ret_1d"]
        m = prices.loc[mask, "mkt_ret_1d"]
        if len(r) > 0 and len(m) > 0 and m.notna().sum() > 0:
            beta_series = rolling_downside_beta(r, m, window=252, min_periods=60)
            prices.loc[mask, "down_beta_252d"] = beta_series.values

    # ---------- feature_builder 入力 ----------
    feature_cols = [
        "date",
        "symbol",
        "ret_5d",
        "ret_20d",
        "vol_20d",
        "adv_20d",
        "ret_1d",  # Variant E/F/G 用
        "downside_ret_1d",  # Variant E/F/G 用
        "downside_vol_60d",  # Variant E/F/G 用
        "mkt_ret_1d",  # Variant F/G 用
        "down_beta_252d",  # Variant F/G 用
    ]
    df_feat_input = prices[feature_cols].dropna(subset=["ret_5d", "ret_20d", "vol_20d", "adv_20d"])

    config = FeatureBuilderConfig()
    df_featured = build_feature_matrix(df_feat_input, config)

    # Variant D 用の z-score カラムを事前に生成
    g = df_featured.groupby("date")
    
    # 20日ボラの z-score
    if "vol_20d" in df_featured.columns and "vol_20d_z" not in df_featured.columns:
        df_featured["vol_20d_z"] = g["vol_20d"].transform(_zscore)
    
    # もし beta_252d があるなら同様に（現時点では未実装）
    if "beta_252d" in df_featured.columns and "beta_252d_z" not in df_featured.columns:
        df_featured["beta_252d_z"] = g["beta_252d"].transform(_zscore)

    # ① z_lin と rank_only の両方の score 列を追加
    df_featured = compute_scores_all(
        df_featured,
        base_col="feature_raw",  # ペナルティ適用前のスコアを base として使用
        group_cols=("date",),  # 後で sector 中立にするときは ("date","sector") に変える
        ascending=False,       # 「値が大きいほど rank 上位」なら False
    )

    # ② 既存コード互換のため、当面は z_lin を feature_score として使う
    df_featured["feature_score"] = df_featured["score_z_lin"]

    # NaT行の除去（latest契約やjoinで事故るため必須）
    nat_n_before = df_featured["date"].isna().sum()
    if nat_n_before > 0:
        import logging
        logging.warning(
            f"build_features: {nat_n_before} rows with NaT date detected, dropping them"
        )
        print(f"[WARNING] {nat_n_before} rows with NaT date detected, dropping them")
    
    df_featured = df_featured[df_featured["date"].notna()].copy()
    
    # アサーション（date列がすべて有効であることを確認）
    nat_n_after = df_featured["date"].isna().sum()
    if nat_n_after > 0:
        raise RuntimeError(f"build_features: {nat_n_after} NaT rows remain after drop. This should not happen.")
    
    # date列がdatetime64[ns]であることを確認（timezone禁止）
    if df_featured["date"].dtype != "datetime64[ns]":
        df_featured["date"] = pd.to_datetime(df_featured["date"]).dt.tz_localize(None)

    out_path = Path("data/processed/daily_feature_scores.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_featured.to_parquet(out_path, index=False)

    print("feature matrix saved to:", out_path)
    print(f"[INFO] Saved {len(df_featured)} rows (NaT rows dropped: {nat_n_before})")
    print(df_featured.tail())


if __name__ == "__main__":
    main()
