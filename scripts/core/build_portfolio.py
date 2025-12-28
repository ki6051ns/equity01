# scripts/core/build_portfolio.py

from datetime import date
import sys
from pathlib import Path

import pandas as pd

# scripts ディレクトリをパスに追加
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# プロジェクトルートもパスに追加（scripts.core をインポートするため）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio


def main():
    feat_path = Path("data/processed/daily_feature_scores.parquet")
    df_features = pd.read_parquet(feat_path)

    # 日付をdatetimeに変換
    df_features["date"] = pd.to_datetime(df_features["date"])

    cfg = ScoringEngineConfig()

    print("ポートフォリオ構築中...")
    df_port = build_daily_portfolio(df_features, cfg)
    print(f"ポートフォリオ構築完了: {len(df_port)} rows")

    # ペーパートレード用に trading_date と decision_date を追加
    # T日のポートフォリオは、T-1日に決めたという前提
    df_port["trading_date"] = df_port["date"]
    df_port["decision_date"] = df_port["trading_date"] - pd.tseries.offsets.BDay(1)

    # 【③ 最重要】latest解釈の固定：date列を正規化・ソートしてから保存
    # - date列をdatetimeに正規化（timezoneなし）
    # - date列で昇順ソートしてから保存
    # - 実運用では daily_portfolio_guarded.parquet の date 列の max(date) の行のみを使用する（契約レベル）
    # - latest専用ファイル作成・完了フラグ・営業日判定は不要
    df_port["date"] = pd.to_datetime(df_port["date"]).dt.normalize()
    df_port = df_port.sort_values("date").reset_index(drop=True)

    out_path = Path("data/processed/daily_portfolio_guarded.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_port.to_parquet(out_path, index=False)

    print("daily portfolio saved to:", out_path)
    print(df_port.tail())


if __name__ == "__main__":
    main()
