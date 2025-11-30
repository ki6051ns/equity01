# scripts/build_portfolio.py

from datetime import date

import pandas as pd
from pathlib import Path

from scoring_engine import ScoringEngineConfig, build_daily_portfolio
from event_guard import EventGuard


def main():
    feat_path = Path("data/processed/daily_feature_scores.parquet")
    df_features = pd.read_parquet(feat_path)

    # EventGuard を初期化
    guard = EventGuard()

    # 各日付に対して決算除外を適用
    df_features["date"] = pd.to_datetime(df_features["date"])
    
    # 決算銘柄を除外（各日付ごと）
    excluded_by_date = {}
    for trade_date in df_features["date"].dt.date.unique():
        excluded = guard.get_excluded_symbols(trade_date)
        if excluded:
            excluded_by_date[trade_date] = excluded
    
    # 除外対象の銘柄をフィルタ
    if excluded_by_date:
        mask = pd.Series(True, index=df_features.index)
        for trade_date, excluded in excluded_by_date.items():
            date_mask = df_features["date"].dt.date == trade_date
            symbol_mask = ~df_features["symbol"].isin(excluded)
            mask = mask & (~date_mask | symbol_mask)
        df_features = df_features[mask].copy()
        print(f"決算銘柄除外: {len(df_features)} rows remaining")

    cfg = ScoringEngineConfig()

    print("ポートフォリオ構築中...")
    df_port = build_daily_portfolio(df_features, cfg)
    print(f"ポートフォリオ構築完了: {len(df_port)} rows")

    # ヘッジ比率を計算（各日付ごと）
    df_port["date"] = pd.to_datetime(df_port["date"])
    df_port["hedge_ratio"] = df_port["date"].dt.date.apply(guard.get_hedge_ratio)
    df_port["inverse_symbol"] = guard.inverse_symbol

    # ペーパートレード用に trading_date と decision_date を追加
    # T日のポートフォリオは、T-1日に決めたという前提
    df_port["trading_date"] = df_port["date"]
    df_port["decision_date"] = df_port["trading_date"] - pd.tseries.offsets.BDay(1)

    out_path = Path("data/processed/daily_portfolio_guarded.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_port.to_parquet(out_path, index=False)

    print("daily portfolio (with EventGuard) saved to:", out_path)
    print(df_port.tail())
    
    # ヘッジ比率のサマリ
    if "hedge_ratio" in df_port.columns:
        hedge_summary = df_port.groupby("date")["hedge_ratio"].first()
        print("\nヘッジ比率サマリ:")
        print(f"  ヘッジが必要な日数: {(hedge_summary > 0).sum()}")
        print(f"  最大ヘッジ比率: {hedge_summary.max():.2f}")
        print(f"  平均ヘッジ比率: {hedge_summary[hedge_summary > 0].mean():.2f}" if (hedge_summary > 0).any() else "  平均ヘッジ比率: 0.00")


if __name__ == "__main__":
    main()
