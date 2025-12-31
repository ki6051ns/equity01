"""
read_latest.py

core成果物（daily_portfolio_guarded.parquet）の最新日を読み込む。
"""
from pathlib import Path
from typing import Optional

import pandas as pd


def read_latest_portfolio(portfolio_path: Optional[Path] = None) -> pd.DataFrame:
    """
    daily_portfolio_guarded.parquet の最新日（max(date)）の行を読み込む。
    
    Parameters
    ----------
    portfolio_path : Path, optional
        ポートフォリオファイルのパス。デフォルトは data/processed/daily_portfolio_guarded.parquet
    
    Returns
    -------
    pd.DataFrame
        最新日のポートフォリオ（date, symbol, weight など）
    """
    if portfolio_path is None:
        portfolio_path = Path("data/processed/daily_portfolio_guarded.parquet")
    
    if not portfolio_path.exists():
        raise FileNotFoundError(f"ポートフォリオファイルが見つかりません: {portfolio_path}")
    
    df = pd.read_parquet(portfolio_path)
    
    # date列をdatetimeに変換
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        latest_date = df["date"].max()
        df_latest = df[df["date"] == latest_date].copy()
    else:
        raise KeyError("'date' 列が見つかりません")
    
    return df_latest


if __name__ == "__main__":
    df = read_latest_portfolio()
    print(f"最新日: {df['date'].iloc[0]}")
    print(f"銘柄数: {len(df)}")
    print(f"合計ウェイト: {df['weight'].sum():.4f}")
    print("\n先頭10行:")
    print(df[["date", "symbol", "weight"]].head(10))
