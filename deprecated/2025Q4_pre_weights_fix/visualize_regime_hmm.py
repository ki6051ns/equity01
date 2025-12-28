#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/visualize_regime_hmm.py

HMMレジームクラスタリング結果の可視化

regime_labels.parquet と regime_stats.json を読み込み、
レジームの時系列推移、統計、分布などを可視化します。
"""

import sys
from pathlib import Path
import json

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # 非対話的バックエンド
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

DATA_DIR = Path("data/processed")
OUTPUT_DIR = Path("data/processed/regime_plots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_regime_data() -> tuple:
    """
    レジームデータを読み込む
    
    Returns
    -------
    tuple
        (df_regime, stats_dict) のタプル
    """
    labels_path = DATA_DIR / "regime_labels.parquet"
    stats_path = DATA_DIR / "regime_stats.json"
    
    if not labels_path.exists():
        raise FileNotFoundError(
            f"{labels_path} がありません。先に build_regime_hmm.py を実行してください。"
        )
    
    df = pd.read_parquet(labels_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # TOPIXリターンを読み込む（存在しない場合）
    if "tpx_ret_cc" not in df.columns:
        print("[INFO] TOPIX returns not found in regime_labels. Loading from cross4...")
        cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
        if cross4_path.exists():
            df_cross4 = pd.read_parquet(cross4_path)
            if "trade_date" in df_cross4.columns:
                df_cross4 = df_cross4.rename(columns={"trade_date": "date"})
            df_cross4["date"] = pd.to_datetime(df_cross4["date"])
            
            if "tpx_ret_cc" in df_cross4.columns:
                df_tpx = df_cross4[["date", "tpx_ret_cc"]].copy()
                df = df.merge(df_tpx, on="date", how="left")
                print(f"[INFO] Merged TOPIX returns: {df['tpx_ret_cc'].notna().sum()} days")
            else:
                # index_tpx_daily.parquetから取得
                tpx_path = DATA_DIR / "index_tpx_daily.parquet"
                if tpx_path.exists():
                    df_tpx = pd.read_parquet(tpx_path)
                    if "trade_date" in df_tpx.columns:
                        df_tpx = df_tpx.rename(columns={"trade_date": "date"})
                    df_tpx["date"] = pd.to_datetime(df_tpx["date"])
                    if "tpx_ret_cc" in df_tpx.columns:
                        df = df.merge(df_tpx[["date", "tpx_ret_cc"]], on="date", how="left")
                        print(f"[INFO] Loaded TOPIX returns from index_tpx_daily: {df['tpx_ret_cc'].notna().sum()} days")
                    else:
                        print("[WARN] tpx_ret_cc column not found. TOPIX returns will not be available.")
                else:
                    print("[WARN] TOPIX data files not found. TOPIX returns will not be available.")
        else:
            print("[WARN] cross4 data not found. TOPIX returns will not be available.")
    
    stats = {}
    if stats_path.exists():
        with open(stats_path, 'r', encoding='utf-8') as f:
            stats = json.load(f)
    
    print(f"[INFO] Loaded regime labels: {len(df)} days")
    print(f"[INFO] Regimes: {sorted(df['regime'].unique())}")
    
    return df, stats


def plot_regime_timeline(df: pd.DataFrame) -> plt.Figure:
    """
    レジームの時系列推移を可視化
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    
    # 1. レジーム遷移
    ax1.plot(df["date"], df["regime"], marker='o', markersize=2, linewidth=0.5, alpha=0.7)
    ax1.set_ylabel("Regime", fontsize=12)
    ax1.set_title("Regime Timeline (HMM Classification)", fontsize=14, fontweight="bold")
    ax1.set_yticks([0, 1, 2])
    ax1.grid(True, alpha=0.3)
    
    # レジーム名があれば凡例に追加
    if "regime_name" in df.columns:
        regime_names = df[["regime", "regime_name"]].drop_duplicates().sort_values("regime")
        for _, row in regime_names.iterrows():
            ax1.plot([], [], label=f"Regime {int(row['regime'])}: {row['regime_name']}", alpha=0.7)
        ax1.legend(loc='upper left', fontsize=10)
    
    # 2. αとレジームの重ね合わせ
    ax2_twin = ax2.twinx()
    
    # αをプロット
    ax2.plot(df["date"], df["alpha"] * 100, label="Daily Alpha (%)", linewidth=1, alpha=0.6, color="#2E86AB")
    ax2.fill_between(df["date"], 0, df["alpha"] * 100, alpha=0.2, color="#2E86AB")
    ax2.set_ylabel("Daily Alpha (%)", fontsize=12, color="#2E86AB")
    ax2.tick_params(axis='y', labelcolor="#2E86AB")
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax2.grid(True, alpha=0.3)
    
    # レジームを背景色で表示
    colors = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}  # 弱/普通/強
    for regime in sorted(df["regime"].unique()):
        mask = df["regime"] == regime
        for i in range(len(df)):
            if mask.iloc[i]:
                ax2_twin.axvspan(
                    df["date"].iloc[i], 
                    df["date"].iloc[i] + pd.Timedelta(days=1),
                    alpha=0.2, 
                    color=colors[int(regime)],
                    linewidth=0
                )
    
    ax2_twin.set_ylabel("Regime", fontsize=12)
    ax2_twin.set_yticks([])
    ax2.set_title("Daily Alpha with Regime Background", fontsize=14, fontweight="bold")
    ax2.set_xlabel("Date", fontsize=12)
    
    # 日付フォーマット
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_alpha_by_regime(df: pd.DataFrame) -> plt.Figure:
    """
    レジーム別のα分布を可視化
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # 1. レジーム別αのヒストグラム
    ax1 = axes[0, 0]
    for regime in sorted(df["regime"].unique()):
        regime_name = f"Regime {int(regime)}"
        if "regime_name" in df.columns:
            regime_df = df[df["regime"] == regime]
            if len(regime_df) > 0 and "regime_name" in regime_df.columns:
                regime_name = regime_df["regime_name"].iloc[0]
        
        alpha_values = df[df["regime"] == regime]["alpha"] * 100
        ax1.hist(alpha_values, bins=50, alpha=0.6, label=regime_name, density=True)
    ax1.set_xlabel("Daily Alpha (%)", fontsize=11)
    ax1.set_ylabel("Density", fontsize=11)
    ax1.set_title("Alpha Distribution by Regime", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.axvline(x=0, color='gray', linestyle='--', linewidth=0.5)
    
    # 2. レジーム別αのボックスプロット
    ax2 = axes[0, 1]
    data_for_box = [df[df["regime"] == r]["alpha"] * 100 for r in sorted(df["regime"].unique())]
    labels = [f"Regime {int(r)}" for r in sorted(df["regime"].unique())]
    bp = ax2.boxplot(data_for_box, labels=labels, patch_artist=True)
    colors_box = ["#FF6B6B", "#FFD93D", "#6BCF7F"]
    for patch, color in zip(bp['boxes'], colors_box[:len(bp['boxes'])]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax2.set_ylabel("Daily Alpha (%)", fontsize=11)
    ax2.set_title("Alpha Box Plot by Regime", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    
    # 3. 累積αのレジーム別
    ax3 = axes[1, 0]
    for regime in sorted(df["regime"].unique()):
        regime_mask = df["regime"] == regime
        cum_alpha = (1 + df["alpha"]).cumprod() - 1
        cum_alpha_regime = cum_alpha.copy()
        cum_alpha_regime[~regime_mask] = np.nan
        
        regime_name = f"Regime {int(regime)}"
        if "regime_name" in df.columns:
            regime_df = df[df["regime"] == regime]
            if len(regime_df) > 0 and "regime_name" in regime_df.columns:
                regime_name = regime_df["regime_name"].iloc[0]
        
        ax3.plot(df["date"], cum_alpha_regime * 100, label=regime_name, linewidth=2, alpha=0.8)
    
    ax3.set_xlabel("Date", fontsize=11)
    ax3.set_ylabel("Cumulative Alpha (%)", fontsize=11)
    ax3.set_title("Cumulative Alpha Contribution by Regime", fontsize=12, fontweight="bold")
    ax3.legend(fontsize=10)
    ax3.grid(True, alpha=0.3)
    ax3.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    # 4. レジーム別期間の割合
    ax4 = axes[1, 1]
    regime_counts = df["regime"].value_counts().sort_index()
    regime_counts_pct = regime_counts / len(df) * 100
    
    colors_pie = ["#FF6B6B", "#FFD93D", "#6BCF7F"]
    labels_pie = [f"Regime {int(r)}" for r in regime_counts.index]
    if "regime_name" in df.columns:
        for regime in regime_counts.index:
            regime_df = df[df["regime"] == regime]
            if len(regime_df) > 0 and "regime_name" in regime_df.columns:
                idx = list(regime_counts.index).index(regime)
                labels_pie[idx] = f"Regime {int(regime)}\n{regime_df['regime_name'].iloc[0]}"
    
    ax4.pie(regime_counts_pct, labels=labels_pie, autopct='%1.1f%%', 
            colors=colors_pie[:len(regime_counts)], startangle=90)
    ax4.set_title("Regime Duration Ratio", fontsize=12, fontweight="bold")
    
    plt.tight_layout()
    return fig


def plot_regime_statistics(df: pd.DataFrame, stats: dict) -> plt.Figure:
    """
    レジーム別統計を可視化
    """
    if not stats:
        # 統計がない場合は計算
        stats = {}
        for regime in sorted(df["regime"].unique()):
            df_regime = df[df["regime"] == regime]
            annual_alpha = df_regime["alpha"].mean() * 252
            annual_std = df_regime["alpha"].std() * np.sqrt(252)
            sharpe = annual_alpha / annual_std if annual_std > 0 else np.nan
            avg_dd = df_regime["dd_252"].mean() if "dd_252" in df_regime.columns else np.nan
            
            stats[str(int(regime))] = {
                "annual_alpha_mean": annual_alpha,
                "annual_alpha_sharpe": sharpe,
                "avg_dd_252": avg_dd,
            }
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    regimes = sorted([int(k) for k in stats.keys()])
    
    # 1. 年率α平均
    ax1 = axes[0, 0]
    alpha_values = [stats[str(r)].get("annual_alpha_mean", 0.0) or 0.0 for r in regimes]
    colors = ["#FF6B6B", "#FFD93D", "#6BCF7F"]
    bars = ax1.bar([f"Regime {r}" for r in regimes], [v * 100 for v in alpha_values], 
                   color=colors[:len(regimes)], alpha=0.7)
    ax1.set_ylabel("Annual Alpha (%)", fontsize=11)
    ax1.set_title("Annual Alpha Mean by Regime", fontsize=12, fontweight="bold")
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    # 値ラベルを追加
    for bar, val in zip(bars, alpha_values):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{val*100:+.2f}%',
                ha='center', va='bottom' if height > 0 else 'top', fontsize=10)
    
    # 2. 年率αシャープ
    ax2 = axes[0, 1]
    sharpe_values = [stats[str(r)].get("annual_alpha_sharpe", 0.0) or 0.0 for r in regimes]
    bars = ax2.bar([f"Regime {r}" for r in regimes], sharpe_values,
                   color=colors[:len(regimes)], alpha=0.7)
    ax2.set_ylabel("Annual Alpha Sharpe", fontsize=11)
    ax2.set_title("Annual Alpha Sharpe by Regime", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    # 値ラベルを追加
    for bar, val in zip(bars, sharpe_values):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:+.2f}',
                ha='center', va='bottom' if height > 0 else 'top', fontsize=10)
    
    # 3. 平均ドローダウン
    ax3 = axes[1, 0]
    dd_values = [stats[str(r)].get("avg_dd_252", 0.0) or 0.0 for r in regimes]
    bars = ax3.bar([f"Regime {r}" for r in regimes], [v * 100 for v in dd_values],
                   color=colors[:len(regimes)], alpha=0.7)
    ax3.set_ylabel("Average Drawdown (%)", fontsize=11)
    ax3.set_title("Average Drawdown (252d) by Regime", fontsize=12, fontweight="bold")
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    # 値ラベルを追加
    for bar, val in zip(bars, dd_values):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{val*100:+.2f}%',
                ha='center', va='bottom' if height < 0 else 'top', fontsize=10)
    
    # 4. 特定年のα
    ax4 = axes[1, 1]
    years_data = {}
    for regime in regimes:
        regime_str = str(regime)
        if regime_str in stats:
            years_data[regime] = {
                2018: stats[regime_str].get("alpha_2018", 0.0) or 0.0,
                2022: stats[regime_str].get("alpha_2022", 0.0) or 0.0,
            }
    
    x = np.arange(len(regimes))
    width = 0.35
    if years_data:
        bars1 = ax4.bar(x - width/2, [years_data[r].get(2018, 0.0) * 100 for r in regimes],
                       width, label='2018', color="#2E86AB", alpha=0.7)
        bars2 = ax4.bar(x + width/2, [years_data[r].get(2022, 0.0) * 100 for r in regimes],
                       width, label='2022', color="#A23B72", alpha=0.7)
        ax4.set_ylabel("Annual Alpha (%)", fontsize=11)
        ax4.set_title("Alpha by Year (2018 vs 2022)", fontsize=12, fontweight="bold")
        ax4.set_xticks(x)
        ax4.set_xticklabels([f"Regime {r}" for r in regimes])
        ax4.legend(fontsize=10)
        ax4.grid(True, alpha=0.3, axis='y')
        ax4.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    
    plt.tight_layout()
    return fig


def plot_regime_transitions(df: pd.DataFrame) -> plt.Figure:
    """
    レジーム遷移マトリックスを可視化
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # 1. 遷移マトリックス
    n_regimes = len(df["regime"].unique())
    transition_matrix = np.zeros((n_regimes, n_regimes))
    
    for i in range(len(df) - 1):
        from_regime = int(df["regime"].iloc[i])
        to_regime = int(df["regime"].iloc[i + 1])
        transition_matrix[from_regime, to_regime] += 1
    
    # 正規化（行ごとに確率に変換）
    row_sums = transition_matrix.sum(axis=1, keepdims=True)
    transition_matrix_prob = transition_matrix / (row_sums + 1e-10)
    
    im1 = ax1.imshow(transition_matrix_prob, cmap='Blues', aspect='auto', vmin=0, vmax=1)
    ax1.set_xlabel("To Regime", fontsize=11)
    ax1.set_ylabel("From Regime", fontsize=11)
    ax1.set_title("Regime Transition Matrix (Probability)", fontsize=12, fontweight="bold")
    ax1.set_xticks(range(n_regimes))
    ax1.set_yticks(range(n_regimes))
    ax1.set_xticklabels([f"R{i}" for i in range(n_regimes)])
    ax1.set_yticklabels([f"R{i}" for i in range(n_regimes)])
    
    # 値を表示
    for i in range(n_regimes):
        for j in range(n_regimes):
            text = ax1.text(j, i, f'{transition_matrix_prob[i, j]:.2f}',
                          ha="center", va="center", color="black", fontsize=10)
    
    plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
    
    # 2. 遷移回数
    im2 = ax2.imshow(transition_matrix, cmap='Reds', aspect='auto')
    ax2.set_xlabel("To Regime", fontsize=11)
    ax2.set_ylabel("From Regime", fontsize=11)
    ax2.set_title("Regime Transition Count", fontsize=12, fontweight="bold")
    ax2.set_xticks(range(n_regimes))
    ax2.set_yticks(range(n_regimes))
    ax2.set_xticklabels([f"R{i}" for i in range(n_regimes)])
    ax2.set_yticklabels([f"R{i}" for i in range(n_regimes)])
    
    # 値を表示
    for i in range(n_regimes):
        for j in range(n_regimes):
            text = ax2.text(j, i, f'{int(transition_matrix[i, j])}',
                          ha="center", va="center", color="white" if transition_matrix[i, j] > transition_matrix.max()/2 else "black", fontsize=10)
    
    plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    
    plt.tight_layout()
    return fig


def plot_feature_evolution(df: pd.DataFrame) -> plt.Figure:
    """
    特徴量の時系列推移を可視化（レジーム背景付き）
    """
    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)
    
    features = ['alpha', 'roll_alpha_mean_63', 'roll_alpha_vol_63', 'dd_252']
    titles = ['Daily Alpha', 'Rolling Alpha Mean (63d)', 'Rolling Alpha Volatility (63d)', 'Drawdown (252d)']
    ylabels = ['Alpha', 'Mean', 'Volatility', 'Drawdown']
    
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    
    for idx, (feat, title, ylabel) in enumerate(zip(features, titles, ylabels)):
        ax = axes[idx]
        
        # 特徴量をプロット
        if feat == 'alpha':
            values = df[feat] * 100  # パーセント表示
            ax.plot(df["date"], values, linewidth=1, alpha=0.7, color="#2E86AB")
        elif feat == 'dd_252':
            values = df[feat] * 100  # パーセント表示
            ax.plot(df["date"], values, linewidth=1, alpha=0.7, color="#A23B72")
            ax.fill_between(df["date"], 0, values, alpha=0.2, color="#A23B72")
        else:
            values = df[feat] * 100 if 'alpha' in feat else df[feat]
            ax.plot(df["date"], values, linewidth=1, alpha=0.7, color="#2E86AB")
        
        # レジーム背景を追加
        ax_twin = ax.twinx()
        for regime in sorted(df["regime"].unique()):
            mask = df["regime"] == regime
            for i in range(len(df)):
                if mask.iloc[i]:
                    ax_twin.axvspan(
                        df["date"].iloc[i],
                        df["date"].iloc[i] + pd.Timedelta(days=1),
                        alpha=0.15,
                        color=colors_regime[int(regime)],
                        linewidth=0
                    )
        
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)
        if feat in ['alpha', 'dd_252']:
            ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        ax_twin.set_yticks([])
    
    axes[-1].set_xlabel("Date", fontsize=11)
    axes[-1].xaxis.set_major_locator(mdates.YearLocator())
    axes[-1].xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(axes[-1].xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_alpha_sum(df: pd.DataFrame) -> plt.Figure:
    """
    相対αの60日・120日合計推移を可視化
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    
    # 60日合計
    df['alpha_sum_60d'] = df['alpha'].rolling(window=60, min_periods=1).sum()
    ax1.plot(df["date"], df['alpha_sum_60d'] * 100, linewidth=1.5, alpha=0.8, color="#2E86AB", label="60-day Sum")
    ax1.fill_between(df["date"], 0, df['alpha_sum_60d'] * 100, alpha=0.2, color="#2E86AB")
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.set_ylabel("60-day Sum Alpha (%)", fontsize=12, color="#2E86AB")
    ax1.set_title("Rolling Sum Alpha: 60-day", fontsize=14, fontweight="bold")
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='y', labelcolor="#2E86AB")
    
    # 120日合計
    df['alpha_sum_120d'] = df['alpha'].rolling(window=120, min_periods=1).sum()
    ax2.plot(df["date"], df['alpha_sum_120d'] * 100, linewidth=1.5, alpha=0.8, color="#A23B72", label="120-day Sum")
    ax2.fill_between(df["date"], 0, df['alpha_sum_120d'] * 100, alpha=0.2, color="#A23B72")
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax2.set_ylabel("120-day Sum Alpha (%)", fontsize=12, color="#A23B72")
    ax2.set_xlabel("Date", fontsize=12)
    ax2.set_title("Rolling Sum Alpha: 120-day", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='y', labelcolor="#A23B72")
    
    # レジーム背景を追加
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for idx, ax in enumerate([ax1, ax2]):
        ax_twin = ax.twinx()
        for regime in sorted(df["regime"].unique()):
            mask = df["regime"] == regime
            for i in range(len(df)):
                if mask.iloc[i]:
                    ax_twin.axvspan(
                        df["date"].iloc[i],
                        df["date"].iloc[i] + pd.Timedelta(days=1),
                        alpha=0.15,
                        color=colors_regime[int(regime)],
                        linewidth=0
                    )
        ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_alpha_sum_comparison(df: pd.DataFrame) -> plt.Figure:
    """
    60日と120日の合計を比較表示
    """
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # 計算
    df['alpha_sum_60d'] = df['alpha'].rolling(window=60, min_periods=1).sum()
    df['alpha_sum_120d'] = df['alpha'].rolling(window=120, min_periods=1).sum()
    
    # プロット
    ax.plot(df["date"], df['alpha_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#2E86AB", label="60-day Sum", linestyle="-")
    ax.plot(df["date"], df['alpha_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#A23B72", label="120-day Sum", linestyle="-")
    
    ax.fill_between(df["date"], 0, df['alpha_sum_60d'] * 100, alpha=0.15, color="#2E86AB")
    ax.fill_between(df["date"], 0, df['alpha_sum_120d'] * 100, alpha=0.15, color="#A23B72")
    
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.set_ylabel("Rolling Sum Alpha (%)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title("Rolling Sum Alpha Comparison: 60-day vs 120-day", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # レジーム背景を追加
    ax_twin = ax.twinx()
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for regime in sorted(df["regime"].unique()):
        mask = df["regime"] == regime
        for i in range(len(df)):
            if mask.iloc[i]:
                ax_twin.axvspan(
                    df["date"].iloc[i],
                    df["date"].iloc[i] + pd.Timedelta(days=1),
                    alpha=0.1,
                    color=colors_regime[int(regime)],
                    linewidth=0
                )
    ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_tpx_sum(df: pd.DataFrame) -> plt.Figure:
    """
    TOPIXリターンの60日・120日合計推移を可視化
    """
    if "tpx_ret_cc" not in df.columns:
        # TOPIXリターンがない場合は空のFigureを返す
        fig, ax = plt.subplots(figsize=(16, 8))
        ax.text(0.5, 0.5, "TOPIX returns data not available", 
                ha='center', va='center', fontsize=14)
        ax.set_title("Rolling Sum TOPIX Returns: 60-day & 120-day", fontsize=14, fontweight="bold")
        return fig
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    
    # 60日合計
    df['tpx_sum_60d'] = df['tpx_ret_cc'].rolling(window=60, min_periods=1).sum()
    ax1.plot(df["date"], df['tpx_sum_60d'] * 100, linewidth=1.5, alpha=0.8, color="#F18F01", label="60-day Sum")
    ax1.fill_between(df["date"], 0, df['tpx_sum_60d'] * 100, alpha=0.2, color="#F18F01")
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.set_ylabel("60-day Sum TOPIX Return (%)", fontsize=12, color="#F18F01")
    ax1.set_title("Rolling Sum TOPIX Returns: 60-day", fontsize=14, fontweight="bold")
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='y', labelcolor="#F18F01")
    
    # 120日合計
    df['tpx_sum_120d'] = df['tpx_ret_cc'].rolling(window=120, min_periods=1).sum()
    ax2.plot(df["date"], df['tpx_sum_120d'] * 100, linewidth=1.5, alpha=0.8, color="#C73E1D", label="120-day Sum")
    ax2.fill_between(df["date"], 0, df['tpx_sum_120d'] * 100, alpha=0.2, color="#C73E1D")
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax2.set_ylabel("120-day Sum TOPIX Return (%)", fontsize=12, color="#C73E1D")
    ax2.set_xlabel("Date", fontsize=12)
    ax2.set_title("Rolling Sum TOPIX Returns: 120-day", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis='y', labelcolor="#C73E1D")
    
    # レジーム背景を追加
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for idx, ax in enumerate([ax1, ax2]):
        ax_twin = ax.twinx()
        for regime in sorted(df["regime"].unique()):
            mask = df["regime"] == regime
            for i in range(len(df)):
                if mask.iloc[i]:
                    ax_twin.axvspan(
                        df["date"].iloc[i],
                        df["date"].iloc[i] + pd.Timedelta(days=1),
                        alpha=0.15,
                        color=colors_regime[int(regime)],
                        linewidth=0
                    )
        ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_tpx_sum_comparison(df: pd.DataFrame) -> plt.Figure:
    """
    60日と120日のTOPIXリターン合計を比較表示
    """
    if "tpx_ret_cc" not in df.columns:
        # TOPIXリターンがない場合は空のFigureを返す
        fig, ax = plt.subplots(figsize=(16, 8))
        ax.text(0.5, 0.5, "TOPIX returns data not available", 
                ha='center', va='center', fontsize=14)
        ax.set_title("Rolling Sum TOPIX Returns Comparison: 60-day vs 120-day", fontsize=14, fontweight="bold")
        return fig
    
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # 計算
    df['tpx_sum_60d'] = df['tpx_ret_cc'].rolling(window=60, min_periods=1).sum()
    df['tpx_sum_120d'] = df['tpx_ret_cc'].rolling(window=120, min_periods=1).sum()
    
    # プロット
    ax.plot(df["date"], df['tpx_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#F18F01", label="TOPIX 60-day Sum", linestyle="-")
    ax.plot(df["date"], df['tpx_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#C73E1D", label="TOPIX 120-day Sum", linestyle="-")
    
    ax.fill_between(df["date"], 0, df['tpx_sum_60d'] * 100, alpha=0.15, color="#F18F01")
    ax.fill_between(df["date"], 0, df['tpx_sum_120d'] * 100, alpha=0.15, color="#C73E1D")
    
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.set_ylabel("Rolling Sum TOPIX Return (%)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title("Rolling Sum TOPIX Returns Comparison: 60-day vs 120-day", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # レジーム背景を追加
    ax_twin = ax.twinx()
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for regime in sorted(df["regime"].unique()):
        mask = df["regime"] == regime
        for i in range(len(df)):
            if mask.iloc[i]:
                ax_twin.axvspan(
                    df["date"].iloc[i],
                    df["date"].iloc[i] + pd.Timedelta(days=1),
                    alpha=0.1,
                    color=colors_regime[int(regime)],
                    linewidth=0
                )
    ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_sum_alpha_vs_tpx(df: pd.DataFrame) -> plt.Figure:
    """
    TOPIXリターンと相対αの120日・60日合計推移を同じグラフに表示
    """
    # TOPIXリターンがない場合は警告を表示
    if "tpx_ret_cc" not in df.columns:
        fig, ax = plt.subplots(figsize=(16, 8))
        ax.text(0.5, 0.5, "TOPIX returns data not available", 
                ha='center', va='center', fontsize=14)
        ax.set_title("Rolling Sum: Alpha vs TOPIX (60-day & 120-day)", fontsize=14, fontweight="bold")
        return fig
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), sharex=True)
    
    # 計算
    df['alpha_sum_60d'] = df['alpha'].rolling(window=60, min_periods=1).sum()
    df['alpha_sum_120d'] = df['alpha'].rolling(window=120, min_periods=1).sum()
    df['tpx_sum_60d'] = df['tpx_ret_cc'].rolling(window=60, min_periods=1).sum()
    df['tpx_sum_120d'] = df['tpx_ret_cc'].rolling(window=120, min_periods=1).sum()
    
    # 60日合計
    ax1.plot(df["date"], df['alpha_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#2E86AB", label="Alpha 60-day Sum", linestyle="-")
    ax1.plot(df["date"], df['tpx_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#F18F01", label="TOPIX 60-day Sum", linestyle="-")
    
    ax1.fill_between(df["date"], 0, df['alpha_sum_60d'] * 100, alpha=0.15, color="#2E86AB")
    ax1.fill_between(df["date"], 0, df['tpx_sum_60d'] * 100, alpha=0.15, color="#F18F01")
    
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.set_ylabel("60-day Sum (%)", fontsize=12)
    ax1.set_title("Rolling Sum: Alpha vs TOPIX (60-day)", fontsize=14, fontweight="bold")
    ax1.legend(fontsize=11, loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # 120日合計
    ax2.plot(df["date"], df['alpha_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#A23B72", label="Alpha 120-day Sum", linestyle="-")
    ax2.plot(df["date"], df['tpx_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#C73E1D", label="TOPIX 120-day Sum", linestyle="-")
    
    ax2.fill_between(df["date"], 0, df['alpha_sum_120d'] * 100, alpha=0.15, color="#A23B72")
    ax2.fill_between(df["date"], 0, df['tpx_sum_120d'] * 100, alpha=0.15, color="#C73E1D")
    
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax2.set_ylabel("120-day Sum (%)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=12)
    ax2.set_title("Rolling Sum: Alpha vs TOPIX (120-day)", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11, loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    # レジーム背景を追加
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for ax in [ax1, ax2]:
        ax_twin = ax.twinx()
        for regime in sorted(df["regime"].unique()):
            mask = df["regime"] == regime
            for i in range(len(df)):
                if mask.iloc[i]:
                    ax_twin.axvspan(
                        df["date"].iloc[i],
                        df["date"].iloc[i] + pd.Timedelta(days=1),
                        alpha=0.1,
                        color=colors_regime[int(regime)],
                        linewidth=0
                    )
        ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def plot_rolling_sum_alpha_vs_tpx_combined(df: pd.DataFrame) -> plt.Figure:
    """
    TOPIXリターンと相対αの120日・60日合計推移を4本すべて同じグラフに表示
    """
    # TOPIXリターンがない場合は警告を表示
    if "tpx_ret_cc" not in df.columns:
        fig, ax = plt.subplots(figsize=(16, 8))
        ax.text(0.5, 0.5, "TOPIX returns data not available", 
                ha='center', va='center', fontsize=14)
        ax.set_title("Rolling Sum: Alpha vs TOPIX (All Periods)", fontsize=14, fontweight="bold")
        return fig
    
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # 計算
    df['alpha_sum_60d'] = df['alpha'].rolling(window=60, min_periods=1).sum()
    df['alpha_sum_120d'] = df['alpha'].rolling(window=120, min_periods=1).sum()
    df['tpx_sum_60d'] = df['tpx_ret_cc'].rolling(window=60, min_periods=1).sum()
    df['tpx_sum_120d'] = df['tpx_ret_cc'].rolling(window=120, min_periods=1).sum()
    
    # プロット（4本すべて）
    ax.plot(df["date"], df['alpha_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#2E86AB", label="Alpha 60-day Sum", linestyle="-")
    ax.plot(df["date"], df['alpha_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#A23B72", label="Alpha 120-day Sum", linestyle="-")
    ax.plot(df["date"], df['tpx_sum_60d'] * 100, linewidth=2, alpha=0.8, 
            color="#F18F01", label="TOPIX 60-day Sum", linestyle="--")
    ax.plot(df["date"], df['tpx_sum_120d'] * 100, linewidth=2, alpha=0.8, 
            color="#C73E1D", label="TOPIX 120-day Sum", linestyle="--")
    
    # 塗りつぶし（αのみ）
    ax.fill_between(df["date"], 0, df['alpha_sum_60d'] * 100, alpha=0.1, color="#2E86AB")
    ax.fill_between(df["date"], 0, df['alpha_sum_120d'] * 100, alpha=0.1, color="#A23B72")
    
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.set_ylabel("Rolling Sum (%)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title("Rolling Sum: Alpha vs TOPIX (60-day & 120-day Combined)", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # レジーム背景を追加
    ax_twin = ax.twinx()
    colors_regime = {0: "#FF6B6B", 1: "#FFD93D", 2: "#6BCF7F"}
    for regime in sorted(df["regime"].unique()):
        mask = df["regime"] == regime
        for i in range(len(df)):
            if mask.iloc[i]:
                ax_twin.axvspan(
                    df["date"].iloc[i],
                    df["date"].iloc[i] + pd.Timedelta(days=1),
                    alpha=0.08,
                    color=colors_regime[int(regime)],
                    linewidth=0
                )
    ax_twin.set_yticks([])
    
    # 日付フォーマット
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def print_regime_summary(df: pd.DataFrame, stats: dict):
    """
    レジームサマリーを表示
    """
    print("\n" + "=" * 80)
    print("=== レジームサマリー ===")
    print("=" * 80)
    
    for regime in sorted(df["regime"].unique()):
        df_regime = df[df["regime"] == regime]
        regime_name = f"Regime {int(regime)}"
        if "regime_name" in df_regime.columns and len(df_regime) > 0:
            regime_name = f"Regime {int(regime)} ({df_regime['regime_name'].iloc[0]})"
        
        print(f"\n【{regime_name}】")
        print(f"  期間: {df_regime['date'].min().date()} ～ {df_regime['date'].max().date()}")
        print(f"  日数: {len(df_regime)} ({len(df_regime)/len(df)*100:.1f}%)")
        
        if str(int(regime)) in stats:
            stat = stats[str(int(regime))]
            print(f"  年率α平均: {stat.get('annual_alpha_mean', 0.0) or 0.0:+.4%}" if stat.get('annual_alpha_mean') is not None else "  年率α平均: N/A")
            print(f"  年率αシャープ: {stat.get('annual_alpha_sharpe', 0.0) or 0.0:+.4f}" if stat.get('annual_alpha_sharpe') is not None else "  年率αシャープ: N/A")
            print(f"  平均DD(252): {stat.get('avg_dd_252', 0.0) or 0.0:+.4%}" if stat.get('avg_dd_252') is not None else "  平均DD(252): N/A")
            print(f"  2018年α: {stat.get('alpha_2018', 0.0) or 0.0:+.4%}" if stat.get('alpha_2018') is not None else "  2018年α: N/A")
            print(f"  2022年α: {stat.get('alpha_2022', 0.0) or 0.0:+.4%}" if stat.get('alpha_2022') is not None else "  2022年α: N/A")
    
    # 60日・120日合計の統計も表示
    print("\n【Rolling Sum Alpha Statistics】")
    df['alpha_sum_60d'] = df['alpha'].rolling(window=60, min_periods=1).sum()
    df['alpha_sum_120d'] = df['alpha'].rolling(window=120, min_periods=1).sum()
    
    print(f"  60-day Sum Alpha:")
    print(f"    平均: {df['alpha_sum_60d'].mean()*100:+.2f}%")
    print(f"    標準偏差: {df['alpha_sum_60d'].std()*100:+.2f}%")
    print(f"    最大: {df['alpha_sum_60d'].max()*100:+.2f}%")
    print(f"    最小: {df['alpha_sum_60d'].min()*100:+.2f}%")
    
    print(f"\n  120-day Sum Alpha:")
    print(f"    平均: {df['alpha_sum_120d'].mean()*100:+.2f}%")
    print(f"    標準偏差: {df['alpha_sum_120d'].std()*100:+.2f}%")
    print(f"    最大: {df['alpha_sum_120d'].max()*100:+.2f}%")
    print(f"    最小: {df['alpha_sum_120d'].min()*100:+.2f}%")
    
    # TOPIXリターンの60日・120日合計の統計も表示
    if "tpx_ret_cc" in df.columns:
        print("\n【Rolling Sum TOPIX Returns Statistics】")
        df['tpx_sum_60d'] = df['tpx_ret_cc'].rolling(window=60, min_periods=1).sum()
        df['tpx_sum_120d'] = df['tpx_ret_cc'].rolling(window=120, min_periods=1).sum()
        
        print(f"  60-day Sum TOPIX Return:")
        print(f"    平均: {df['tpx_sum_60d'].mean()*100:+.2f}%")
        print(f"    標準偏差: {df['tpx_sum_60d'].std()*100:+.2f}%")
        print(f"    最大: {df['tpx_sum_60d'].max()*100:+.2f}%")
        print(f"    最小: {df['tpx_sum_60d'].min()*100:+.2f}%")
        
        print(f"\n  120-day Sum TOPIX Return:")
        print(f"    平均: {df['tpx_sum_120d'].mean()*100:+.2f}%")
        print(f"    標準偏差: {df['tpx_sum_120d'].std()*100:+.2f}%")
        print(f"    最大: {df['tpx_sum_120d'].max()*100:+.2f}%")
        print(f"    最小: {df['tpx_sum_120d'].min()*100:+.2f}%")


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== HMMレジームクラスタリング結果の可視化 ===")
    print("=" * 80)
    
    # データ読み込み
    print("\n[STEP 1] Loading regime data...")
    df, stats = load_regime_data()
    
    # 可視化
    print("\n[STEP 2] Creating visualizations...")
    
    # 1. レジームタイムライン
    print("  [1/5] Plotting regime timeline...")
    fig1 = plot_regime_timeline(df)
    fig1_path = OUTPUT_DIR / "regime_timeline.png"
    fig1.savefig(fig1_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig1_path}")
    plt.close(fig1)
    
    # 2. レジーム別α分布
    print("  [2/5] Plotting alpha by regime...")
    fig2 = plot_alpha_by_regime(df)
    fig2_path = OUTPUT_DIR / "alpha_by_regime.png"
    fig2.savefig(fig2_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig2_path}")
    plt.close(fig2)
    
    # 3. レジーム統計
    print("  [3/5] Plotting regime statistics...")
    fig3 = plot_regime_statistics(df, stats)
    fig3_path = OUTPUT_DIR / "regime_statistics.png"
    fig3.savefig(fig3_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig3_path}")
    plt.close(fig3)
    
    # 4. レジーム遷移
    print("  [4/5] Plotting regime transitions...")
    fig4 = plot_regime_transitions(df)
    fig4_path = OUTPUT_DIR / "regime_transitions.png"
    fig4.savefig(fig4_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig4_path}")
    plt.close(fig4)
    
    # 5. 特徴量の時系列推移
    print("  [5/7] Plotting feature evolution...")
    fig5 = plot_feature_evolution(df)
    fig5_path = OUTPUT_DIR / "feature_evolution.png"
    fig5.savefig(fig5_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig5_path}")
    plt.close(fig5)
    
    # 6. 60日・120日合計（個別）
    print("  [6/7] Plotting rolling sum alpha (60d & 120d)...")
    fig6 = plot_rolling_alpha_sum(df)
    fig6_path = OUTPUT_DIR / "rolling_sum_alpha_60d_120d.png"
    fig6.savefig(fig6_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig6_path}")
    plt.close(fig6)
    
    # 7. 60日・120日合計（比較）
    print("  [7/9] Plotting rolling sum alpha comparison...")
    fig7 = plot_rolling_alpha_sum_comparison(df)
    fig7_path = OUTPUT_DIR / "rolling_sum_alpha_comparison.png"
    fig7.savefig(fig7_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig7_path}")
    plt.close(fig7)
    
    # 8. TOPIXリターン60日・120日合計（個別）
    print("  [8/9] Plotting rolling sum TOPIX returns (60d & 120d)...")
    fig8 = plot_rolling_tpx_sum(df)
    fig8_path = OUTPUT_DIR / "rolling_sum_tpx_60d_120d.png"
    fig8.savefig(fig8_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig8_path}")
    plt.close(fig8)
    
    # 9. TOPIXリターン60日・120日合計（比較）
    print("  [9/11] Plotting rolling sum TOPIX returns comparison...")
    fig9 = plot_rolling_tpx_sum_comparison(df)
    fig9_path = OUTPUT_DIR / "rolling_sum_tpx_comparison.png"
    fig9.savefig(fig9_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig9_path}")
    plt.close(fig9)
    
    # 10. α vs TOPIX 60日・120日合計（個別）
    print("  [10/11] Plotting rolling sum: Alpha vs TOPIX (separate)...")
    fig10 = plot_rolling_sum_alpha_vs_tpx(df)
    fig10_path = OUTPUT_DIR / "rolling_sum_alpha_vs_tpx_separate.png"
    fig10.savefig(fig10_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig10_path}")
    plt.close(fig10)
    
    # 11. α vs TOPIX 60日・120日合計（統合）
    print("  [11/11] Plotting rolling sum: Alpha vs TOPIX (combined)...")
    fig11 = plot_rolling_sum_alpha_vs_tpx_combined(df)
    fig11_path = OUTPUT_DIR / "rolling_sum_alpha_vs_tpx_combined.png"
    fig11.savefig(fig11_path, dpi=150, bbox_inches='tight')
    print(f"    Saved: {fig11_path}")
    plt.close(fig11)
    
    # サマリー表示
    print_regime_summary(df, stats)
    
    print("\n" + "=" * 80)
    print("=== 可視化完了 ===")
    print("=" * 80)
    print(f"\nすべてのプロットは {OUTPUT_DIR} に保存されました。")


if __name__ == "__main__":
    main()

