"""
paper_trade 結果に相対αを後乗せするスクリプト（β/OLS抜きのシンプル版）

既存の paper_trade.py を直接は変更せず、
run_paper_trade() の日次結果（df_daily）を読み出し、
それに TOPIX 日次リターンを join して相対αを計算する。

結果を data/processed/paper_trade_with_alpha_beta.parquet に保存。
"""
from pathlib import Path
from typing import Tuple

import pandas as pd
import sys
import os

# scripts ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paper_trade import PaperTradeConfig, run_paper_trade


def load_tpx_returns(path: str = "data/processed/index_tpx_daily.parquet") -> pd.DataFrame:
    """TOPIX（日次C→Cリターン）の読み込み."""
    df = pd.read_parquet(path)
    # 念のため日付ソート
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df[["trade_date", "tpx_ret_cc"]]


def merge_portfolio_with_tpx(
    df_daily: pd.DataFrame, df_tpx: pd.DataFrame
) -> pd.DataFrame:
    """
    paper_trade の日次リターンと TOPIX 日次リターンを同時点でマージ。
    """
    # index に trading_date を持っている前提
    df_daily = df_daily.reset_index().rename(columns={"trading_date": "trade_date"})
    df_daily = df_daily.sort_values("trade_date")

    print(f"\npaper_trade 結果: {len(df_daily)} 日分")
    print(
        f"日付範囲: {df_daily['trade_date'].min()} ～ {df_daily['trade_date'].max()}"
    )

    print(f"\nTOPIX データ: {len(df_tpx)} 日分")
    print(
        f"日付範囲: {df_tpx['trade_date'].min()} ～ {df_tpx['trade_date'].max()}"
    )

    df = df_daily.merge(df_tpx, on="trade_date", how="inner")
    df = df.sort_values("trade_date").reset_index(drop=True)

    print(f"\nマージ後: {len(df)} 日分")

    # ポートフォリオ C→C リターン（paper_trade の daily_return をそのまま採用）
    df["port_ret_cc"] = df["daily_return"]

    return df


def add_cumulative_and_relative_alpha(df: pd.DataFrame) -> Tuple[pd.DataFrame, float]:
    """
    累積リターンと、TOPIXに対する累積超過リターン（relative alpha）を計算。

    - cum_port: ポートフォリオの累積リターン（1を基準とした倍率）
    - cum_tpx:  TOPIXの累積リターン（同上）
    - rel_alpha_daily: 日次の超過リターン (port_ret_cc - tpx_ret_cc)
    - relative_alpha_total: 期間トータルの累積超過リターン
        = (cum_port - 1) - (cum_tpx - 1)
    """
    df = df.copy()

    df["cum_port"] = (1.0 + df["port_ret_cc"]).cumprod()
    df["cum_tpx"] = (1.0 + df["tpx_ret_cc"]).cumprod()

    # 日次の超過リターン
    df["rel_alpha_daily"] = df["port_ret_cc"] - df["tpx_ret_cc"]

    # 期間トータルの累積超過リターン（「TOPIXにどれだけ勝った/負けたか」）
    cum_port = df["cum_port"].iloc[-1]
    cum_tpx = df["cum_tpx"].iloc[-1]
    relative_alpha_total = (cum_port - 1.0) - (cum_tpx - 1.0)

    return df, relative_alpha_total


def print_summary(df: pd.DataFrame, relative_alpha_total: float) -> None:
    """ポートフォリオ vs TOPIX vs 相対α のサマリ出力（シンプル版）."""
    start = df["trade_date"].min()
    end = df["trade_date"].max()
    n = len(df)

    mu_port = df["port_ret_cc"].mean()
    mu_tpx = df["tpx_ret_cc"].mean()
    mu_rel = df["rel_alpha_daily"].mean()

    cum_port = df["cum_port"].iloc[-1]
    cum_tpx = df["cum_tpx"].iloc[-1]

    print("\n=== サマリ統計（β/OLS抜きのシンプル版） ===")
    print(f"期間: {start} ～ {end}")
    print(f"日数: {n}")
    print("\n日次平均リターン:")
    print(f"  ポートフォリオ: {mu_port:+.6f}")
    print(f"  TOPIX        : {mu_tpx:+.6f}")
    print(f"  日次相対α    : {mu_rel:+.6f}")

    print("\n累積リターン（最終日）:")
    print(f"  ポートフォリオ: {cum_port:.4f} ({(cum_port - 1.0)*100:+.2f}%)")
    print(f"  TOPIX        : {cum_tpx:.4f} ({(cum_tpx  - 1.0)*100:+.2f}%)")
    print(
        f"  累積相対α    : {(relative_alpha_total)*100:+.2f}% "
        "(= Port累積 - TOPIX累積)"
    )


def main() -> None:
    print("paper_trade を実行中...")
    cfg = PaperTradeConfig()
    df_daily, summary = run_paper_trade(cfg)

    # TOPIX C→C リターンをロード
    df_tpx = load_tpx_returns("data/processed/index_tpx_daily.parquet")

    # 同時点マージ & port_ret_cc / tpx_ret_cc を揃える
    df = merge_portfolio_with_tpx(df_daily, df_tpx)

    # 累積リターンと相対αを追加
    df, relative_alpha_total = add_cumulative_and_relative_alpha(df)

    # 保存（ファイル名は互換性のためそのまま利用）
    out = Path("data/processed/paper_trade_with_alpha_beta.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    print(f"\n相対α計算結果を保存しました: {out}")
    print("\n先頭5行:")
    print(
        df[
            [
                "trade_date",
                "port_ret_cc",
                "tpx_ret_cc",
                "rel_alpha_daily",
                "cum_port",
                "cum_tpx",
            ]
        ].head()
    )

    print("\n末尾5行:")
    print(
        df[
            [
                "trade_date",
                "port_ret_cc",
                "tpx_ret_cc",
                "rel_alpha_daily",
                "cum_port",
                "cum_tpx",
            ]
        ].tail()
    )

    # サマリ出力（β/OLS は完全に無視）
    print_summary(df, relative_alpha_total)


if __name__ == "__main__":
    main()
