# scripts/build_portfolio.py

import pandas as pd
from pathlib import Path

from scoring_engine import ScoringEngineConfig, build_daily_portfolio
from event_guard import EventGuardConfig, apply_event_guard


def main():
    feat_path = Path("data/processed/daily_feature_scores.parquet")
    df_features = pd.read_parquet(feat_path)

    cfg = ScoringEngineConfig(
        max_names_per_day=30,
        weighting_scheme="equal",
    )

    df_port = build_daily_portfolio(df_features, cfg)

    # EventGuard を適用
    # Note: Windowsでは'aux'は予約語のため'events'を使用
    earnings_path = Path("data/events/earnings_calendar.csv")
    macro_path = Path("data/events/macro_events.csv")
    vix_path = Path("data/processed/vix.parquet")

    earnings = pd.read_csv(earnings_path) if earnings_path.exists() else pd.DataFrame()
    macro = pd.read_csv(macro_path) if macro_path.exists() else pd.DataFrame()
    vix = pd.read_parquet(vix_path) if vix_path.exists() else pd.DataFrame()

    guard_cfg = EventGuardConfig()
    df_port_guarded = apply_event_guard(
        df_port,
        guard_cfg,
        earnings_calendar=earnings,
        macro_calendar=macro,
        vix=vix,
    )

    # ペーパートレード用に trading_date と decision_date を追加
    # T日のポートフォリオは、T-1日に決めたという前提
    df_port_guarded["trading_date"] = df_port_guarded["date"]
    df_port_guarded["decision_date"] = df_port_guarded["trading_date"] - pd.tseries.offsets.BDay(1)

    out_path = Path("data/processed/daily_portfolio_guarded.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_port_guarded.to_parquet(out_path, index=False)

    print("daily portfolio (with EventGuard) saved to:", out_path)
    print(df_port_guarded.tail())


if __name__ == "__main__":
    main()
