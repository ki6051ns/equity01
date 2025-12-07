#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/visualize_bpi_126d.py

126営業日ローリング最大ドローダウンベースのBPIを可視化するスクリプト。

rank_only と variant_cross3 の比較を含む。
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 非対話型バックエンド（画像保存用）
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# フォント設定（日本語対応を試みるが、フォールバックあり）
plt.rcParams["axes.unicode_minus"] = False

# データパス
DATA_DIR = Path("data/processed")
MERGED_BPI_PATH = DATA_DIR / "bpi_rank_only_vs_cross3_vs_topix_126d.parquet"
OUTPUT_DIR = Path("research/reports/bpi_126d")


def load_bpi_data() -> pd.DataFrame:
    """マージ済みBPIデータを読み込む（TOPIX含む）"""
    # まずはTOPIXを含むファイルを試す
    if MERGED_BPI_PATH.exists():
        df = pd.read_parquet(MERGED_BPI_PATH)
    else:
        # フォールバック: TOPIXなしのファイル
        fallback_path = DATA_DIR / "bpi_rank_only_vs_cross3_126d.parquet"
        if fallback_path.exists():
            print(f"[WARN] Using fallback file without TOPIX: {fallback_path}")
            df = pd.read_parquet(fallback_path)
        else:
            raise FileNotFoundError(
                f"BPI file not found: {MERGED_BPI_PATH} or {fallback_path}\n"
                f"Please run scripts/calc_bpi_126d.py first."
            )

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def plot_bpi_comparison(df: pd.DataFrame):
    """rank_only、cross3、TOPIX のBPI推移を比較"""
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.plot(
        df.index,
        df["bpi_rank_only"],
        label="rank_only",
        linewidth=1.5,
        alpha=0.8,
        color="#2E86AB",
    )
    ax.plot(
        df.index,
        df["bpi_cross3"],
        label="variant_cross3",
        linewidth=1.5,
        alpha=0.8,
        color="#A23B72",
    )
    
    # TOPIXが利用可能な場合
    if "bpi_topix" in df.columns:
        ax.plot(
            df.index,
            df["bpi_topix"],
            label="TOPIX",
            linewidth=1.5,
            alpha=0.8,
            color="#F18F01",
            linestyle="--",
        )

    title = "BPI Comparison: rank_only vs variant_cross3"
    if "bpi_topix" in df.columns:
        title += " vs TOPIX"
    title += " (126-day rolling)"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("BPI", fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

    # 年ごとにグリッド線を追加
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def plot_drawdown_comparison(df: pd.DataFrame):
    """ドローダウンの比較（TOPIX含む）"""
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.fill_between(
        df.index,
        0,
        df["drawdown_rank_only"],
        label="rank_only DD",
        alpha=0.5,
        color="#2E86AB",
    )
    ax.fill_between(
        df.index,
        0,
        df["drawdown_cross3"],
        label="variant_cross3 DD",
        alpha=0.5,
        color="#A23B72",
    )
    
    # TOPIXが利用可能な場合
    if "drawdown_topix" in df.columns:
        ax.fill_between(
            df.index,
            0,
            df["drawdown_topix"],
            label="TOPIX DD",
            alpha=0.5,
            color="#F18F01",
        )

    ax.plot(
        df.index,
        df["drawdown_rank_only"],
        linewidth=1.0,
        alpha=0.7,
        color="#1B5E7A",
    )
    ax.plot(
        df.index,
        df["drawdown_cross3"],
        linewidth=1.0,
        alpha=0.7,
        color="#7A2B5E",
    )
    
    if "drawdown_topix" in df.columns:
        ax.plot(
            df.index,
            df["drawdown_topix"],
            linewidth=1.0,
            alpha=0.7,
            color="#C73E1D",
            linestyle="--",
        )

    title = "Drawdown Comparison (126-day rolling peak-based)"
    if "drawdown_topix" in df.columns:
        title += " - Including TOPIX"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Drawdown", fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def plot_bpi_scatter(df: pd.DataFrame):
    """rank_only と cross3 のBPI散布図（相関関係）"""
    fig, ax = plt.subplots(figsize=(8, 8))

    ax.scatter(
        df["bpi_rank_only"],
        df["bpi_cross3"],
        alpha=0.5,
        s=10,
        color="#2E86AB",
    )

    # 相関係数
    corr = df["bpi_rank_only"].corr(df["bpi_cross3"])

    # 1:1ライン
    max_val = max(df["bpi_rank_only"].max(), df["bpi_cross3"].max())
    ax.plot([0, max_val], [0, max_val], "r--", linewidth=1.5, alpha=0.7, label="1:1 line")

    ax.set_xlabel("BPI (rank_only)", fontsize=12)
    ax.set_ylabel("BPI (variant_cross3)", fontsize=12)
    ax.set_title(
        f"BPI Scatter Plot: rank_only vs cross3\nCorrelation: {corr:.4f}",
        fontsize=14,
        fontweight="bold",
    )
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal", adjustable="box")

    plt.tight_layout()
    return fig


def plot_bpi_scatter_vs_topix(df: pd.DataFrame):
    """ポートフォリオとTOPIXのBPI散布図（相関関係）"""
    if "bpi_topix" not in df.columns:
        # TOPIXがない場合は空の図を返す
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.text(0.5, 0.5, "TOPIX data not available", ha="center", va="center", fontsize=14)
        ax.set_title("BPI Scatter Plot vs TOPIX", fontsize=14, fontweight="bold")
        plt.tight_layout()
        return fig

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    # rank_only vs TOPIX
    axes[0].scatter(
        df["bpi_rank_only"],
        df["bpi_topix"],
        alpha=0.5,
        s=10,
        color="#2E86AB",
    )
    corr1 = df["bpi_rank_only"].corr(df["bpi_topix"])
    max_val1 = max(df["bpi_rank_only"].max(), df["bpi_topix"].max())
    axes[0].plot([0, max_val1], [0, max_val1], "r--", linewidth=1.5, alpha=0.7, label="1:1 line")
    axes[0].set_xlabel("BPI (rank_only)", fontsize=12)
    axes[0].set_ylabel("BPI (TOPIX)", fontsize=12)
    axes[0].set_title(
        f"rank_only vs TOPIX\nCorrelation: {corr1:.4f}",
        fontsize=12,
        fontweight="bold",
    )
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_aspect("equal", adjustable="box")

    # cross3 vs TOPIX
    axes[1].scatter(
        df["bpi_cross3"],
        df["bpi_topix"],
        alpha=0.5,
        s=10,
        color="#A23B72",
    )
    corr2 = df["bpi_cross3"].corr(df["bpi_topix"])
    max_val2 = max(df["bpi_cross3"].max(), df["bpi_topix"].max())
    axes[1].plot([0, max_val2], [0, max_val2], "r--", linewidth=1.5, alpha=0.7, label="1:1 line")
    axes[1].set_xlabel("BPI (variant_cross3)", fontsize=12)
    axes[1].set_ylabel("BPI (TOPIX)", fontsize=12)
    axes[1].set_title(
        f"variant_cross3 vs TOPIX\nCorrelation: {corr2:.4f}",
        fontsize=12,
        fontweight="bold",
    )
    axes[1].legend(fontsize=10)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_aspect("equal", adjustable="box")

    plt.tight_layout()
    return fig


def plot_bpi_rolling_stats(df: pd.DataFrame, window_days: int = 252):
    """ローリング統計（平均・標準偏差）を表示（TOPIX含む）"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # ローリング平均
    rolling_mean_rank = df["bpi_rank_only"].rolling(window=window_days, min_periods=1).mean()
    rolling_mean_cross3 = df["bpi_cross3"].rolling(window=window_days, min_periods=1).mean()

    axes[0].plot(
        df.index,
        rolling_mean_rank,
        label="rank_only (rolling mean)",
        linewidth=1.5,
        color="#2E86AB",
    )
    axes[0].plot(
        df.index,
        rolling_mean_cross3,
        label="variant_cross3 (rolling mean)",
        linewidth=1.5,
        color="#A23B72",
    )
    
    if "bpi_topix" in df.columns:
        rolling_mean_topix = df["bpi_topix"].rolling(window=window_days, min_periods=1).mean()
        axes[0].plot(
            df.index,
            rolling_mean_topix,
            label="TOPIX (rolling mean)",
            linewidth=1.5,
            color="#F18F01",
            linestyle="--",
        )
    
    axes[0].set_ylabel(f"BPI ({window_days}-day rolling mean)", fontsize=11)
    title = f"BPI Rolling Statistics ({window_days} business days)"
    if "bpi_topix" in df.columns:
        title += " - Including TOPIX"
    axes[0].set_title(title, fontsize=14, fontweight="bold")
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)

    # ローリング標準偏差
    rolling_std_rank = df["bpi_rank_only"].rolling(window=window_days, min_periods=1).std()
    rolling_std_cross3 = df["bpi_cross3"].rolling(window=window_days, min_periods=1).std()

    axes[1].plot(
        df.index,
        rolling_std_rank,
        label="rank_only (rolling std)",
        linewidth=1.5,
        color="#2E86AB",
    )
    axes[1].plot(
        df.index,
        rolling_std_cross3,
        label="variant_cross3 (rolling std)",
        linewidth=1.5,
        color="#A23B72",
    )
    
    if "bpi_topix" in df.columns:
        rolling_std_topix = df["bpi_topix"].rolling(window=window_days, min_periods=1).std()
        axes[1].plot(
            df.index,
            rolling_std_topix,
            label="TOPIX (rolling std)",
            linewidth=1.5,
            color="#F18F01",
            linestyle="--",
        )
    
    axes[1].set_xlabel("Date", fontsize=12)
    axes[1].set_ylabel(f"BPI ({window_days}-day rolling std)", fontsize=11)
    axes[1].legend(fontsize=10)
    axes[1].grid(True, alpha=0.3)

    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    axes[1].xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(axes[1].xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.tight_layout()
    return fig


def plot_bpi_distribution(df: pd.DataFrame):
    """BPIの分布（ヒストグラム）を比較"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # rank_only
    axes[0].hist(
        df["bpi_rank_only"].dropna(),
        bins=50,
        alpha=0.7,
        color="#2E86AB",
        edgecolor="black",
        linewidth=0.5,
    )
    axes[0].axvline(
        df["bpi_rank_only"].mean(),
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Mean: {df['bpi_rank_only'].mean():.4f}",
    )
    axes[0].axvline(
        df["bpi_rank_only"].median(),
        color="orange",
        linestyle="--",
        linewidth=2,
        label=f"Median: {df['bpi_rank_only'].median():.4f}",
    )
    axes[0].set_xlabel("BPI", fontsize=11)
    axes[0].set_ylabel("Frequency", fontsize=11)
    axes[0].set_title("rank_only BPI Distribution", fontsize=12, fontweight="bold")
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3, axis="y")

    # cross3
    axes[1].hist(
        df["bpi_cross3"].dropna(),
        bins=50,
        alpha=0.7,
        color="#A23B72",
        edgecolor="black",
        linewidth=0.5,
    )
    axes[1].axvline(
        df["bpi_cross3"].mean(),
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Mean: {df['bpi_cross3'].mean():.4f}",
    )
    axes[1].axvline(
        df["bpi_cross3"].median(),
        color="orange",
        linestyle="--",
        linewidth=2,
        label=f"Median: {df['bpi_cross3'].median():.4f}",
    )
    axes[1].set_xlabel("BPI", fontsize=11)
    axes[1].set_ylabel("Frequency", fontsize=11)
    axes[1].set_title("variant_cross3 BPI Distribution", fontsize=12, fontweight="bold")
    axes[1].legend(fontsize=9)
    axes[1].grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    return fig


def print_statistics(df: pd.DataFrame):
    """統計情報を表示（TOPIX含む）"""
    print("\n" + "=" * 80)
    print("=== BPI統計情報 ===")
    print("=" * 80)

    cols_to_print = ["bpi_rank_only", "bpi_cross3"]
    if "bpi_topix" in df.columns:
        cols_to_print.append("bpi_topix")

    for col in cols_to_print:
        print(f"\n【{col}】")
        data = df[col].dropna()
        print(f"  データ数: {len(data)}")
        print(f"  平均: {data.mean():.6f}")
        print(f"  中央値: {data.median():.6f}")
        print(f"  標準偏差: {data.std():.6f}")
        print(f"  最小値: {data.min():.6f}")
        print(f"  最大値: {data.max():.6f}")
        print(f"  25%分位点: {data.quantile(0.25):.6f}")
        print(f"  75%分位点: {data.quantile(0.75):.6f}")

    print(f"\n【相関関係】")
    if "bpi_rank_only" in df.columns and "bpi_cross3" in df.columns:
        corr = df["bpi_rank_only"].corr(df["bpi_cross3"])
        print(f"  rank_only vs cross3: {corr:.6f}")
    if "bpi_rank_only" in df.columns and "bpi_topix" in df.columns:
        corr = df["bpi_rank_only"].corr(df["bpi_topix"])
        print(f"  rank_only vs topix: {corr:.6f}")
    if "bpi_cross3" in df.columns and "bpi_topix" in df.columns:
        corr = df["bpi_cross3"].corr(df["bpi_topix"])
        print(f"  cross3 vs topix: {corr:.6f}")

    print(f"\n【差分統計】")
    if "bpi_rank_only" in df.columns and "bpi_cross3" in df.columns:
        diff = df["bpi_rank_only"] - df["bpi_cross3"]
        print(f"  rank_only - cross3")
        print(f"    平均: {diff.mean():.6f}")
        print(f"    標準偏差: {diff.std():.6f}")
        print(f"    最小値: {diff.min():.6f}")
        print(f"    最大値: {diff.max():.6f}")
    if "bpi_rank_only" in df.columns and "bpi_topix" in df.columns:
        diff = df["bpi_rank_only"] - df["bpi_topix"]
        print(f"\n  rank_only - topix")
        print(f"    平均: {diff.mean():.6f}")
        print(f"    標準偏差: {diff.std():.6f}")
        print(f"    最小値: {diff.min():.6f}")
        print(f"    最大値: {diff.max():.6f}")
    if "bpi_cross3" in df.columns and "bpi_topix" in df.columns:
        diff = df["bpi_cross3"] - df["bpi_topix"]
        print(f"\n  cross3 - topix")
        print(f"    平均: {diff.mean():.6f}")
        print(f"    標準偏差: {diff.std():.6f}")
        print(f"    最小値: {diff.min():.6f}")
        print(f"    最大値: {diff.max():.6f}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="Visualize BPI (126-day rolling drawdown-based) for rank_only and variant_cross3"
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

    print("BPIデータを読み込み中...")
    df = load_bpi_data()

    print(f"データ期間: {df.index.min().date()} ～ {df.index.max().date()}")
    print(f"データ行数: {len(df)}")

    # 統計情報を表示
    print_statistics(df)

    # 可視化
    print("\n" + "=" * 80)
    print("=== 可視化開始 ===")
    print("=" * 80)

    plots = [
        ("bpi_comparison", plot_bpi_comparison),
        ("drawdown_comparison", plot_drawdown_comparison),
        ("bpi_scatter", plot_bpi_scatter),
    ]
    
    # TOPIXとの比較散布図を追加（TOPIXデータがある場合）
    if "bpi_topix" in df.columns:
        plots.append(("bpi_scatter_vs_topix", plot_bpi_scatter_vs_topix))
    
    plots.extend([
        ("bpi_rolling_stats", lambda df: plot_bpi_rolling_stats(df, window_days=252)),
        ("bpi_distribution", plot_bpi_distribution),
    ])

    total_plots = len(plots)
    for i, (name, plot_func) in enumerate(plots, 1):
        print(f"\n[{i}/{total_plots}] Generating {name} plot...")
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

