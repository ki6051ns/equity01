#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/visualize_inverse_etf_126d.py

インバースETF2種類（1569.T、1356.T）の126営業日ローリング合計リターンを可視化するスクリプト。
プラスの日次リターンのみを合計します。

1569.T: TOPIXインバース -1x
1356.T: TOPIXダブルインバース -2x
"""

import argparse
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 非対話型バックエンド（画像保存用）
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# フォント設定
plt.rcParams["axes.unicode_minus"] = False

# データパス
DATA_DIR = Path("data/raw/equities")
OUTPUT_DIR = Path("research/reports/inverse_etf_126d")

# インバースETF設定
TICKERS = {
    "1569.T": "TOPIX Inverse -1x",
    "1356.T": "TOPIX Double Inverse -2x",
}
DATE_COL = "date"
PRICE_COL = "adj_close"
WINDOW_DAYS = 126  # 126営業日（半年）


def load_etf_data(ticker: str) -> pd.DataFrame:
    """インバースETFの価格データを読み込む"""
    path = DATA_DIR / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Price file not found for {ticker}: {path}")

    df = pd.read_parquet(path)
    if DATE_COL not in df.columns:
        raise ValueError(f"{ticker}: column '{DATE_COL}' not found")

    df = df.copy()
    df[DATE_COL] = pd.to_datetime(df[DATE_COL])
    df = df.sort_values(DATE_COL)

    if PRICE_COL not in df.columns:
        raise ValueError(f"{ticker}: column '{PRICE_COL}' not found")

    return df


def compute_rolling_sum_return(df: pd.DataFrame, price_col: str, window: int = WINDOW_DAYS) -> pd.Series:
    """126営業日ローリング合計リターンを計算（プラスのリターンのみ）"""
    # 日次リターン
    daily_return = df[price_col].pct_change()
    
    # プラスのリターンのみ（負の値は0にする）
    positive_return = daily_return.clip(lower=0.0)
    
    # ローリング合計（プラスのリターンのみ）
    rolling_sum = positive_return.rolling(window=window, min_periods=1).sum()
    
    return rolling_sum


def prepare_data() -> pd.DataFrame:
    """2つのインバースETFのデータを準備してマージ"""
    dfs = []
    
    for ticker, name in TICKERS.items():
        print(f"[INFO] Loading {ticker} ({name})...")
        df = load_etf_data(ticker)
        
        # 日次リターン
        df[f"ret_{ticker}"] = df[PRICE_COL].pct_change()
        
        # 126日ローリング合計リターン
        df[f"rolling_sum_{ticker}"] = compute_rolling_sum_return(df, PRICE_COL, WINDOW_DAYS)
        
        # 必要な列だけ残す
        df = df[[DATE_COL, f"ret_{ticker}", f"rolling_sum_{ticker}", PRICE_COL]].copy()
        df = df.rename(columns={PRICE_COL: f"price_{ticker}"})
        
        dfs.append(df)
    
    # 日付でマージ
    merged = dfs[0]
    for df in dfs[1:]:
        merged = pd.merge(merged, df, on=DATE_COL, how="inner")
    
    return merged.sort_values(DATE_COL)


def plot_rolling_sum_comparison(df: pd.DataFrame):
    """126日ローリング合計リターンの比較"""
    fig, ax = plt.subplots(figsize=(14, 6))

    colors = {
        "1569.T": "#2E86AB",
        "1356.T": "#A23B72",
    }

    for ticker, name in TICKERS.items():
        col = f"rolling_sum_{ticker}"
        if col in df.columns:
            ax.plot(
                df[DATE_COL],
                df[col] * 100,  # パーセント表示
                label=f"{ticker} ({name})",
                linewidth=1.5,
                alpha=0.8,
                color=colors[ticker],
            )

    ax.axhline(y=0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title(f"126-Day Rolling Sum Return (Positive Only): Inverse ETFs", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Cumulative Return (%) - Positive Only", fontsize=12)
    ax.set_ylim(bottom=0)  # プラスのみなので0以上に設定
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    # 年ごとにグリッド線を追加
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def plot_rolling_sum_scatter(df: pd.DataFrame):
    """1569.Tと1356.Tの126日ローリング合計リターンの散布図"""
    fig, ax = plt.subplots(figsize=(8, 8))

    col_1569 = "rolling_sum_1569.T"
    col_1356 = "rolling_sum_1356.T"

    if col_1569 not in df.columns or col_1356 not in df.columns:
        ax.text(0.5, 0.5, "Data not available", ha="center", va="center", fontsize=14)
        ax.set_title("Rolling Sum Return Scatter Plot", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    ax.scatter(
        df[col_1569] * 100,
        df[col_1356] * 100,
        alpha=0.5,
        s=10,
        color="#2E86AB",
    )

    # 相関係数
    corr = df[col_1569].corr(df[col_1356])

    # 2:1ライン（1356.Tは1569.Tの約2倍の関係）
    max_val = max(df[col_1569].max(), df[col_1356].max())
    ax.plot([0, max_val*100], [0, max_val*200], "r--", linewidth=1.5, alpha=0.7, label="2:1 line (expected)")

    ax.set_xlabel("1569.T Rolling Sum Return (%) - Positive Only", fontsize=12)
    ax.set_ylabel("1356.T Rolling Sum Return (%) - Positive Only", fontsize=12)
    ax.set_title(
        f"Rolling Sum Return Scatter Plot (Positive Only)\nCorrelation: {corr:.4f}",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlim(left=0)  # プラスのみなので0以上
    ax.set_ylim(bottom=0)  # プラスのみなので0以上
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color="black", linestyle="--", linewidth=0.8, alpha=0.3)
    ax.axvline(x=0, color="black", linestyle="--", linewidth=0.8, alpha=0.3)

    plt.tight_layout()
    return fig


def plot_price_comparison(df: pd.DataFrame):
    """価格の推移比較（正規化）"""
    fig, ax = plt.subplots(figsize=(14, 6))

    colors = {
        "1569.T": "#2E86AB",
        "1356.T": "#A23B72",
    }

    for ticker, name in TICKERS.items():
        price_col = f"price_{ticker}"
        if price_col in df.columns:
            # 最初の価格で正規化
            normalized = df[price_col] / df[price_col].iloc[0] * 100
            ax.plot(
                df[DATE_COL],
                normalized,
                label=f"{ticker} ({name})",
                linewidth=1.5,
                alpha=0.8,
                color=colors[ticker],
            )

    ax.set_title("Price Comparison (Normalized to 100 at start)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Normalized Price", fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def plot_rolling_sum_statistics(df: pd.DataFrame):
    """126日ローリング合計リターンの統計（ローリング平均・標準偏差）"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    colors = {
        "1569.T": "#2E86AB",
        "1356.T": "#A23B72",
    }

    window_stats = 252  # 統計用のローリングウィンドウ

    # ローリング平均
    for ticker, name in TICKERS.items():
        col = f"rolling_sum_{ticker}"
        if col in df.columns:
            rolling_mean = df[col].rolling(window=window_stats, min_periods=1).mean()
            axes[0].plot(
                df[DATE_COL],
                rolling_mean * 100,
                label=f"{ticker} (rolling mean)",
                linewidth=1.5,
                color=colors[ticker],
            )

    axes[0].axhline(y=0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    axes[0].set_ylabel(f"Rolling Sum Return ({window_stats}-day rolling mean, %) - Positive Only", fontsize=11)
    axes[0].set_title(f"Rolling Sum Return Statistics (Positive Only, {window_stats}-day window)", fontsize=14, fontweight="bold")
    axes[0].set_ylim(bottom=0)  # プラスのみなので0以上
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)

    # ローリング標準偏差
    for ticker, name in TICKERS.items():
        col = f"rolling_sum_{ticker}"
        if col in df.columns:
            rolling_std = df[col].rolling(window=window_stats, min_periods=1).std()
            axes[1].plot(
                df[DATE_COL],
                rolling_std * 100,
                label=f"{ticker} (rolling std)",
                linewidth=1.5,
                color=colors[ticker],
            )

    axes[1].set_xlabel("Date", fontsize=12)
    axes[1].set_ylabel(f"Rolling Sum Return ({window_stats}-day rolling std, %) - Positive Only", fontsize=11)
    axes[1].set_ylim(bottom=0)  # 標準偏差は常に0以上
    axes[1].legend(fontsize=10)
    axes[1].grid(True, alpha=0.3)

    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    axes[1].xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(axes[1].xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def print_statistics(df: pd.DataFrame):
    """統計情報を表示"""
    print("\n" + "=" * 80)
    print("=== 126日ローリング合計リターン統計情報（プラスのみ） ===")
    print("=" * 80)

    for ticker, name in TICKERS.items():
        col = f"rolling_sum_{ticker}"
        if col in df.columns:
            print(f"\n【{ticker} ({name})】")
            data = df[col].dropna()
            print(f"  データ数: {len(data)}")
            print(f"  平均: {data.mean()*100:.4f}%")
            print(f"  中央値: {data.median()*100:.4f}%")
            print(f"  標準偏差: {data.std()*100:.4f}%")
            print(f"  最小値: {data.min()*100:.4f}%")
            print(f"  最大値: {data.max()*100:.4f}%")
            print(f"  25%分位点: {data.quantile(0.25)*100:.4f}%")
            print(f"  75%分位点: {data.quantile(0.75)*100:.4f}%")

    # 相関関係
    col_1569 = "rolling_sum_1569.T"
    col_1356 = "rolling_sum_1356.T"
    if col_1569 in df.columns and col_1356 in df.columns:
        print(f"\n【相関関係】")
        corr = df[col_1569].corr(df[col_1356])
        print(f"  1569.T vs 1356.T: {corr:.6f}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="Visualize 126-day rolling sum returns for inverse ETFs (1569.T, 1356.T)"
    )
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Save plots to directory (default: display only)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="png",
        choices=["png", "pdf", "svg"],
        help="Image format for saved plots (default: png)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for saved images (default: 150)",
    )
    args = parser.parse_args()

    # 出力ディレクトリの準備
    save_dir = None
    if args.save:
        save_dir = Path(args.save)
        save_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Plots will be saved to: {save_dir}")

    print("インバースETFデータを読み込み中...")
    df = prepare_data()

    print(f"データ期間: {df[DATE_COL].min().date()} ～ {df[DATE_COL].max().date()}")
    print(f"データ行数: {len(df)}")

    # 統計情報を表示
    print_statistics(df)

    # 可視化
    print("\n" + "=" * 80)
    print("=== 可視化開始 ===")
    print("=" * 80)

    plots = [
        ("rolling_sum_comparison", plot_rolling_sum_comparison),
        ("rolling_sum_scatter", plot_rolling_sum_scatter),
        ("price_comparison", plot_price_comparison),
        ("rolling_sum_statistics", plot_rolling_sum_statistics),
    ]

    for i, (name, plot_func) in enumerate(plots, 1):
        print(f"\n[{i}/{len(plots)}] Generating {name} plot...")
        fig = plot_func(df)

        if save_dir:
            output_path = save_dir / f"{name}.{args.format}"
            fig.savefig(output_path, dpi=args.dpi, bbox_inches="tight")
            print(f"  Saved: {output_path}")
            plt.close(fig)
        else:
            plt.show()

    print("\n" + "=" * 80)
    print("=== 可視化完了 ===")
    print("=" * 80)
    if save_dir:
        print(f"\nAll plots saved to: {save_dir}")


if __name__ == "__main__":
    main()

