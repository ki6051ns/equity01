# scripts/core/build_portfolio.py

from datetime import date
import sys
import logging
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
from scripts.core.beta_calculator import calculate_portfolio_beta

# 最小候補銘柄数（これ未満ならportfolio生成をスキップ）
MIN_CANDIDATES_PER_DAY = 10


def main():
    feat_path = Path("data/processed/daily_feature_scores.parquet")
    df_features = pd.read_parquet(feat_path)

    # 日付をdatetimeに変換
    df_features["date"] = pd.to_datetime(df_features["date"])

    # 最新日のfeature行数をチェック
    latest_date = df_features["date"].max()
    latest_features = df_features[df_features["date"] == latest_date]
    n_features = len(latest_features)
    
    if n_features < MIN_CANDIDATES_PER_DAY:
        logging.warning(
            f"SKIP_PORTFOLIO_TOO_FEW_FEATURES "
            f"date={latest_date.strftime('%Y-%m-%d')} n={n_features} "
            f"(min={MIN_CANDIDATES_PER_DAY})"
        )
        print(f"[WARNING] ポートフォリオ生成をスキップ: {latest_date.strftime('%Y-%m-%d')} のfeature行数が不足 ({n_features} < {MIN_CANDIDATES_PER_DAY})")
        
        # 既存のportfolioファイルを読み込んで、最新日を確認
        out_path = Path("data/processed/daily_portfolio_guarded.parquet")
        if out_path.exists():
            df_existing = pd.read_parquet(out_path)
            df_existing["date"] = pd.to_datetime(df_existing["date"])
            existing_latest = df_existing["date"].max()
            print(f"[INFO] 既存のportfolio最新日: {existing_latest.strftime('%Y-%m-%d')} (更新なし)")
        else:
            print("[WARNING] 既存のportfolioファイルが見つかりません")
        
        # latest更新なしとして終了（exit code 0で正常終了）
        return

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

    # β計算（latest行のみ）
    latest_date = df_port["date"].max()
    latest_portfolio = df_port[df_port["date"] == latest_date].copy()
    
    print("β計算中...")
    beta_equity_cash, beta_equity_cfd, beta_status, beta_ref_date = calculate_portfolio_beta(
        latest_portfolio,
        benchmark_symbol="1306.T",
        lookback_days=60,
        min_periods=20,
    )
    
    print(f"β計算完了: equity_cash={beta_equity_cash:.3f}, equity_cfd={beta_equity_cfd:.3f}, status={beta_status}")
    
    # latest行にβ系4列を追加（全行に同じ値を設定）
    df_port["beta_equity_cash"] = beta_equity_cash
    df_port["beta_equity_cfd"] = beta_equity_cfd
    df_port["beta_status"] = beta_status
    df_port["beta_ref_date"] = beta_ref_date

    out_path = Path("data/processed/daily_portfolio_guarded.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_port.to_parquet(out_path, index=False)

    print("daily portfolio saved to:", out_path)
    print(f"[INFO] β情報: status={beta_status}, ref_date={beta_ref_date.strftime('%Y-%m-%d') if beta_ref_date else 'N/A'}")
    print(df_port.tail())


if __name__ == "__main__":
    main()
