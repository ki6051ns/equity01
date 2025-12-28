#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
visualize_bpi.py

BPI（Bear Pressure Index）の推移を可視化するスクリプト
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# データパス
BPI_PATH = Path("data/processed/bpi.parquet")

def load_bpi() -> pd.DataFrame:
    """BPIデータを読み込む"""
    if not BPI_PATH.exists():
        raise FileNotFoundError(f"BPI file not found: {BPI_PATH}")
    
    df = pd.read_parquet(BPI_PATH)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    return df


def plot_bpi_full(df: pd.DataFrame):
    """2016〜2025のBPI推移をプロット"""
    plt.figure(figsize=(12, 4))
    plt.plot(df.index, df['bpi'], label='BPI', linewidth=1.5)
    plt.axvspan(
        pd.Timestamp('2018-01-01'),
        pd.Timestamp('2018-12-31'),
        color='red',
        alpha=0.15,
        label='2018 region'
    )
    plt.title("Bear Pressure Index (BPI) 時系列", fontsize=14, fontweight='bold')
    plt.xlabel("日付", fontsize=12)
    plt.ylabel("BPI", fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_bpi_zoom(df: pd.DataFrame):
    """2017〜2020のBPI推移をズーム表示"""
    plt.figure(figsize=(12, 4))
    sub = df.loc['2017':'2020']
    plt.plot(sub.index, sub['bpi'], label='BPI (2017-2020)', linewidth=1.5)
    plt.axvspan(
        pd.Timestamp('2018-01-01'),
        pd.Timestamp('2018-12-31'),
        color='red',
        alpha=0.15,
        label='2018 region'
    )
    plt.title("BPI 2017-2020（2018を強調）", fontsize=14, fontweight='bold')
    plt.xlabel("日付", fontsize=12)
    plt.ylabel("BPI", fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_bpi_smoothed(df: pd.DataFrame):
    """BPIとスムーズ化バージョンを比較"""
    plt.figure(figsize=(14, 6))
    plt.plot(df.index, df['bpi'], label='BPI (daily)', alpha=0.5, linewidth=0.8)
    plt.plot(df.index, df['bpi_21d'], label='BPI 21d MA', linewidth=1.5)
    plt.plot(df.index, df['bpi_63d'], label='BPI 63d MA', linewidth=1.5)
    plt.axvspan(
        pd.Timestamp('2018-01-01'),
        pd.Timestamp('2018-12-31'),
        color='red',
        alpha=0.15,
        label='2018 region'
    )
    plt.title("BPI と移動平均（21日・63日）", fontsize=14, fontweight='bold')
    plt.xlabel("日付", fontsize=12)
    plt.ylabel("BPI", fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def main():
    # データ読み込み
    print("BPIデータを読み込み中...")
    df = load_bpi()
    print(f"データ期間: {df.index.min()} ～ {df.index.max()}")
    print(f"データ行数: {len(df)}")
    
    # 年ごとの平均
    yearly = df['bpi'].groupby(df.index.year).mean()
    print("\n=== 年ごとの平均BPI ===")
    print(yearly)
    
    # プロット1：2016〜2025推移
    print("\n[プロット1] 2016〜2025のBPI推移を表示中...")
    plot_bpi_full(df)
    
    # プロット2：2017〜2020ズーム
    print("\n[プロット2] 2017〜2020のBPI推移を表示中...")
    plot_bpi_zoom(df)
    
    # プロット3：スムーズ化バージョン
    print("\n[プロット3] BPIと移動平均を表示中...")
    plot_bpi_smoothed(df)
    
    print("\n=== 可視化完了 ===")


if __name__ == "__main__":
    main()
