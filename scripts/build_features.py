# scripts/build_features.py

import pandas as pd
from pathlib import Path

from feature_builder import FeatureBuilderConfig, build_feature_matrix
import data_loader


def main():
    prices = data_loader.load_prices()

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

    # ---------- feature_builder 入力 ----------
    feature_cols = [
        "date",
        "symbol",
        "ret_5d",
        "ret_20d",
        "vol_20d",
        "adv_20d",
    ]
    df_feat_input = prices[feature_cols].dropna()

    config = FeatureBuilderConfig()
    df_featured = build_feature_matrix(df_feat_input, config)

    out_path = Path("data/processed/daily_feature_scores.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_featured.to_parquet(out_path, index=False)

    print("feature matrix saved to:", out_path)
    print(df_featured.tail())


if __name__ == "__main__":
    main()
