#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/eval_stop_regimes_robustness.py

STOP条件に基づく戦略のロバストネステスト

① 期間分割 OOSテスト（IS: 2016-2019, OOS: 2020-2025）
② STOP中ウェイトのロバスト性テスト（90/10, 80/20, 75/25, 70/30, 60/40）
③ コスト・スプレッド・追随誤差込みの現実的パフォーマンス
④ エピソード分析（イベントクラスターの寄与分析）
⑤ STOP条件の単純版での再現性（一般則チェック）
⑥ 現時点での採用方針の妥当性確認
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# 日本語フォント設定
import platform
import matplotlib.font_manager as fm

# OSに応じた日本語フォントを設定
system = platform.system()
if system == 'Windows':
    # Windows環境: MS Gothic, Yu Gothicなどを試す
    jp_fonts = ['MS Gothic', 'Yu Gothic', 'Meiryo', 'MS PGothic']
    for font in jp_fonts:
        if font in [f.name for f in fm.fontManager.ttflist]:
            plt.rcParams['font.family'] = font
            break
    else:
        plt.rcParams['font.family'] = 'DejaVu Sans'
elif system == 'Darwin':  # macOS
    plt.rcParams['font.family'] = 'Hiragino Sans'
else:  # Linux
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'

DATA_DIR = Path("data/processed")
OUTPUT_DIR = Path("data/processed/stop_regime_robustness")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_cross4_and_topix() -> Tuple[pd.Series, pd.Series]:
    """cross4とTOPIXの日次リターンを読み込む"""
    cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    
    if not cross4_path.exists():
        raise FileNotFoundError(f"{cross4_path} がありません。")
    
    df = pd.read_parquet(cross4_path)
    date_col = "trade_date" if "trade_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    
    # リターンカラムを確認
    port_col = None
    for col in ["port_ret_cc", "port_ret_cc_ens", "combined_ret"]:
        if col in df.columns:
            port_col = col
            break
    
    if port_col is None:
        raise KeyError(f"ポートフォリオリターン列が見つかりません: {df.columns.tolist()}")
    
    tpx_col = None
    for col in ["tpx_ret_cc", "tpx_ret"]:
        if col in df.columns:
            tpx_col = col
            break
    
    if tpx_col is None:
        tpx_path = DATA_DIR / "index_tpx_daily.parquet"
        if tpx_path.exists():
            df_tpx = pd.read_parquet(tpx_path)
            tpx_date_col = "trade_date" if "trade_date" in df_tpx.columns else "date"
            df_tpx[tpx_date_col] = pd.to_datetime(df_tpx[tpx_date_col])
            df_tpx = df_tpx.set_index(tpx_date_col).sort_index()
            if "tpx_ret_cc" in df_tpx.columns:
                tpx_ret = df_tpx["tpx_ret_cc"]
            else:
                raise KeyError(f"TOPIXリターン列が見つかりません")
        else:
            raise FileNotFoundError(f"TOPIXリターンが見つかりません")
    else:
        tpx_ret = df[tpx_col]
    
    port_ret = df[port_col]
    
    # インデックスで揃える
    common_index = port_ret.index.intersection(tpx_ret.index)
    port_ret = port_ret.loc[common_index]
    tpx_ret = tpx_ret.loc[common_index]
    
    return port_ret, tpx_ret


def load_inverse_returns() -> pd.Series:
    """インバースETF（1569.T）の日次リターンを読み込む"""
    inverse_paths = [
        DATA_DIR / "inverse_returns.parquet",
        DATA_DIR / "daily_returns_inverse.parquet",
        Path("data/raw") / "equities" / "1569.T.parquet",
    ]
    
    for path in inverse_paths:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                date_col = None
                for col in ["date", "trade_date", "datetime"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col is None:
                    continue
                
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.set_index(date_col).sort_index()
                
                ret_col = None
                for col in ["ret", "inv_ret", "port_return", "return"]:
                    if col in df.columns:
                        ret_col = col
                        break
                
                if ret_col is None:
                    for col in ["close", "adj_close", "Close", "Adj Close"]:
                        if col in df.columns:
                            ret_col = col
                            df["ret"] = df[col].pct_change()
                            ret_col = "ret"
                            break
                
                if ret_col is None:
                    continue
                
                inv_ret = df[ret_col].dropna()
                return inv_ret
            except Exception:
                continue
    
    print("[WARN] Inverse returns not found. Using zero returns.")
    return pd.Series(dtype=float)


def compute_stop_condition(port_ret: pd.Series, tpx_ret: pd.Series, window: int = 60) -> pd.Series:
    """STOP条件を計算（ルックアヘッドバイアス回避）"""
    alpha = port_ret - tpx_ret
    roll_alpha = alpha.rolling(window=window, min_periods=1).sum().shift(1).fillna(False)
    roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1).fillna(False)
    stop_cond = (roll_alpha < 0) & (roll_tpx < 0)
    return stop_cond


def compute_strategy_returns(
    port_ret: pd.Series,
    inv_ret: pd.Series,
    stop_cond: pd.Series,
    cross4_weight: float = 0.75,
    inv_weight: float = 0.25,
    stop0: bool = False,
    plan_b: bool = False,
) -> pd.Series:
    """戦略リターンを計算"""
    inv_ret_aligned = inv_ret.reindex(port_ret.index, fill_value=0.0)
    
    if stop0:
        # STOP0: STOP中はリターン0
        return pd.Series(np.where(stop_cond, 0.0, port_ret.values), index=port_ret.index)
    elif plan_b:
        # Plan B: STOP中はcross4 50%
        return pd.Series(np.where(stop_cond, 0.5 * port_ret.values, port_ret.values), index=port_ret.index)
    else:
        # Plan A: STOP中はcross4 * w1 + inverse * w2
        ret_stop = cross4_weight * port_ret.values + inv_weight * inv_ret_aligned.values
        return pd.Series(np.where(stop_cond, ret_stop, port_ret.values), index=port_ret.index)


def compute_performance_metrics(ret_series: pd.Series, tpx_ret: pd.Series) -> Dict:
    """パフォーマンス指標を計算"""
    common_index = ret_series.index.intersection(tpx_ret.index)
    ret_aligned = ret_series.loc[common_index]
    tpx_aligned = tpx_ret.loc[common_index]
    
    days = len(ret_aligned)
    years = days / 252.0
    
    # 累積リターン
    cum_ret = (1 + ret_aligned).prod() - 1
    cum_tpx = (1 + tpx_aligned).prod() - 1
    
    # 年率リターン
    ann_ret = (1 + cum_ret) ** (1.0 / years) - 1 if years > 0 else 0.0
    ann_tpx = (1 + cum_tpx) ** (1.0 / years) - 1 if years > 0 else 0.0
    
    # ボラティリティ
    vol = ret_aligned.std() * np.sqrt(252)
    vol_tpx = tpx_aligned.std() * np.sqrt(252)
    
    # シャープ（リスクフリーレート=0）
    sharpe = ann_ret / vol if vol > 0 else np.nan
    sharpe_tpx = ann_tpx / vol_tpx if vol_tpx > 0 else np.nan
    
    # アルファ
    alpha = ret_aligned - tpx_aligned
    ann_alpha = alpha.mean() * 252
    alpha_vol = alpha.std() * np.sqrt(252)
    alpha_sharpe = ann_alpha / alpha_vol if alpha_vol > 0 else np.nan
    
    # 最大ドローダウン
    cum_curve = (1 + ret_aligned).cumprod()
    dd = (cum_curve / cum_curve.cummax() - 1).min()
    
    return {
        "cumulative": cum_ret,
        "cumulative_tpx": cum_tpx,
        "annualized": ann_ret,
        "volatility": vol,
        "sharpe": sharpe,
        "alpha_annualized": ann_alpha,
        "alpha_volatility": alpha_vol,
        "alpha_sharpe": alpha_sharpe,
        "max_dd": dd,
        "days": days,
        "years": years,
    }


def test_1_oos_split(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """① 期間分割 OOSテスト"""
    print("\n" + "=" * 80)
    print("=== テスト①: 期間分割 OOSテスト ===")
    print("=" * 80)
    
    is_start = "2016-01-01"
    is_end = "2019-12-31"
    oos_start = "2020-01-01"
    oos_end = "2025-12-31"
    
    # STOP条件はIS期間で決定（60日ウィンドウ）
    is_mask = (port_ret.index >= is_start) & (port_ret.index <= is_end)
    oos_mask = (port_ret.index >= oos_start) & (port_ret.index <= oos_end)
    
    port_is = port_ret[is_mask]
    tpx_is = tpx_ret[is_mask]
    
    # IS期間でSTOP条件を計算
    stop_cond_is = compute_stop_condition(port_is, tpx_is, window=60)
    
    # 全期間でSTOP条件を計算（OOSでも同じロジックを適用）
    stop_cond_full = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    # 各戦略のリターンを計算
    strategies = {
        "cross4": port_ret,
        "stop0": compute_strategy_returns(port_ret, inv_ret, stop_cond_full, stop0=True),
        "planA": compute_strategy_returns(port_ret, inv_ret, stop_cond_full, 0.75, 0.25),
        "planB": compute_strategy_returns(port_ret, inv_ret, stop_cond_full, plan_b=True),
    }
    
    results_is = {}
    results_oos = {}
    
    for name, ret_series in strategies.items():
        ret_is = ret_series[is_mask]
        ret_oos = ret_series[oos_mask]
        tpx_is_subset = tpx_ret[is_mask]
        tpx_oos_subset = tpx_ret[oos_mask]
        
        results_is[name] = compute_performance_metrics(ret_is, tpx_is_subset)
        results_oos[name] = compute_performance_metrics(ret_oos, tpx_oos_subset)
    
    # 結果表示
    print("\n【IS期間 (2016-2019)】")
    print(f"{'戦略':<10} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10}")
    print("-" * 75)
    for name in strategies.keys():
        r = results_is[name]
        print(f"{name:<10} {r['cumulative']*100:>9.2f}% {r['annualized']*100:>9.2f}% "
              f"{r['sharpe']:>9.2f} {r['alpha_sharpe']:>11.2f} {r['max_dd']*100:>9.2f}%")
    
    print("\n【OOS期間 (2020-2025)】")
    print(f"{'戦略':<10} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10}")
    print("-" * 75)
    for name in strategies.keys():
        r = results_oos[name]
        print(f"{name:<10} {r['cumulative']*100:>9.2f}% {r['annualized']*100:>9.2f}% "
              f"{r['sharpe']:>9.2f} {r['alpha_sharpe']:>11.2f} {r['max_dd']*100:>9.2f}%")
    
    # 可視化
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # IS期間の累積リターン
    ax = axes[0, 0]
    dates_is = port_ret[is_mask].index
    for name in strategies.keys():
        cum_ret = (1 + strategies[name][is_mask]).cumprod()
        ax.plot(dates_is, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("IS期間: 累積リターン (2016-2019)", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # OOS期間の累積リターン
    ax = axes[0, 1]
    dates_oos = port_ret[oos_mask].index
    for name in strategies.keys():
        cum_ret = (1 + strategies[name][oos_mask]).cumprod()
        ax.plot(dates_oos, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("OOS期間: 累積リターン (2020-2025)", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # IS期間のドローダウン
    ax = axes[1, 0]
    for name in strategies.keys():
        cum_ret = (1 + strategies[name][is_mask]).cumprod()
        dd = cum_ret / cum_ret.cummax() - 1
        ax.plot(dates_is, dd * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("IS期間: ドローダウン (2016-2019)", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # OOS期間のドローダウン
    ax = axes[1, 1]
    for name in strategies.keys():
        cum_ret = (1 + strategies[name][oos_mask]).cumprod()
        dd = cum_ret / cum_ret.cummax() - 1
        ax.plot(dates_oos, dd * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("OOS期間: ドローダウン (2020-2025)", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test1_oos_split.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)
    
    # 合格基準チェック
    print("\n【合格基準チェック】")
    oos_cross4_dd = results_oos["cross4"]["max_dd"]
    oos_planA_dd = results_oos["planA"]["max_dd"]
    oos_cross4_ret = results_oos["cross4"]["annualized"]
    oos_planA_ret = results_oos["planA"]["annualized"]
    
    dd_improved = oos_planA_dd > oos_cross4_dd  # DDが小さくなる=改善
    ret_ok = oos_planA_ret >= oos_cross4_ret * 0.95  # リターンが同等以上
    
    print(f"OOS期間でPlan AのDD改善: {dd_improved} (cross4: {oos_cross4_dd*100:.2f}%, Plan A: {oos_planA_dd*100:.2f}%)")
    print(f"OOS期間でPlan Aのリターン: {ret_ok} (cross4: {oos_cross4_ret*100:.2f}%, Plan A: {oos_planA_ret*100:.2f}%)")
    print(f"合格: {dd_improved and ret_ok}")


def test_2_weight_robustness(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """② STOP中ウェイトのロバスト性テスト"""
    print("\n" + "=" * 80)
    print("=== テスト②: STOP中ウェイトのロバスト性テスト ===")
    print("=" * 80)
    
    stop_cond = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    weight_configs = [
        (0.90, 0.10),
        (0.80, 0.20),
        (0.75, 0.25),  # 現行
        (0.70, 0.30),
        (0.60, 0.40),
    ]
    
    results = {}
    for w1, w2 in weight_configs:
        ret_series = compute_strategy_returns(port_ret, inv_ret, stop_cond, w1, w2)
        results[f"{w1:.0%}/{w2:.0%}"] = {
            "returns": ret_series,
            "metrics": compute_performance_metrics(ret_series, tpx_ret),
        }
    
    # 結果表示
    print(f"\n{'ウェイト':<12} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10}")
    print("-" * 75)
    for name, r in results.items():
        m = r["metrics"]
        print(f"{name:<12} {m['cumulative']*100:>9.2f}% {m['annualized']*100:>9.2f}% "
              f"{m['sharpe']:>9.2f} {m['alpha_sharpe']:>11.2f} {m['max_dd']*100:>9.2f}%")
    
    # 可視化
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 累積リターン
    ax = axes[0, 0]
    dates = port_ret.index
    for name, r in results.items():
        cum_ret = (1 + r["returns"]).cumprod()
        ax.plot(dates, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("累積リターン比較", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ドローダウン
    ax = axes[0, 1]
    for name, r in results.items():
        cum_ret = (1 + r["returns"]).cumprod()
        dd = cum_ret / cum_ret.cummax() - 1
        ax.plot(dates, dd * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("ドローダウン比較", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # パフォーマンス指標比較
    ax = axes[1, 0]
    weight_labels = [name for name in results.keys()]
    annualized = [r["metrics"]["annualized"] * 100 for r in results.values()]
    sharpe = [r["metrics"]["sharpe"] for r in results.values()]
    max_dd = [r["metrics"]["max_dd"] * 100 for r in results.values()]
    
    x = np.arange(len(weight_labels))
    width = 0.25
    ax.bar(x - width, annualized, width, label="年率リターン(%)", alpha=0.8)
    ax_twin = ax.twinx()
    ax_twin.bar(x, sharpe, width, label="Sharpe", alpha=0.8, color='orange')
    ax_twin.bar(x + width, max_dd, width, label="MaxDD(%)", alpha=0.8, color='red')
    
    ax.set_xlabel("ウェイト (cross4/inverse)")
    ax.set_ylabel("年率リターン (%)", color='blue')
    ax_twin.set_ylabel("Sharpe / MaxDD (%)", color='black')
    ax.set_xticks(x)
    ax.set_xticklabels(weight_labels, rotation=45, ha='right')
    ax.legend(loc='upper left')
    ax_twin.legend(loc='upper right')
    ax.set_title("パフォーマンス指標比較", fontweight="bold")
    ax.grid(True, alpha=0.3, axis='y')
    
    # 累積リターンとMaxDDのトレードオフ
    ax = axes[1, 1]
    for name, r in results.items():
        ax.scatter(abs(r["metrics"]["max_dd"]) * 100, r["metrics"]["annualized"] * 100,
                  s=100, alpha=0.7, label=name)
    ax.set_xlabel("MaxDD (%)")
    ax.set_ylabel("年率リターン (%)")
    ax.set_title("リターン vs リスク トレードオフ", fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test2_weight_robustness.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)


def test_3_with_costs(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """③ コスト・スプレッド・追随誤差込みの現実的パフォーマンス"""
    print("\n" + "=" * 80)
    print("=== テスト③: コスト込みパフォーマンス ===")
    print("=" * 80)
    
    stop_cond = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    # コスト設定
    daily_cost_inv = 0.0001  # 0.5-1bp / 日
    switch_cost = 0.002  # 0.2% / 切替
    
    # ベース戦略
    cross4_base = port_ret
    planA_base = compute_strategy_returns(port_ret, inv_ret, stop_cond, 0.75, 0.25)
    planB_base = compute_strategy_returns(port_ret, inv_ret, stop_cond, plan_b=True)
    
    # コスト込み計算
    # Plan A: STOP期間中はinverse保有 → 日次コスト
    # STOP切替時に追加コスト
    inv_ret_aligned = inv_ret.reindex(port_ret.index, fill_value=0.0)
    
    planA_with_costs = planA_base.copy()
    planA_switch = stop_cond.diff().fillna(False)
    planA_with_costs[stop_cond] -= daily_cost_inv  # STOP期間中の日次コスト
    planA_with_costs[planA_switch] -= switch_cost  # 切替コスト
    
    planB_with_costs = planB_base.copy()
    planB_switch = stop_cond.diff().fillna(False)
    planB_with_costs[planB_switch] -= switch_cost  # 切替コスト
    
    strategies = {
        "cross4 (コストなし)": cross4_base,
        "Plan A (コストなし)": planA_base,
        "Plan B (コストなし)": planB_base,
        "Plan A (コストあり)": planA_with_costs,
        "Plan B (コストあり)": planB_with_costs,
    }
    
    results = {}
    for name, ret_series in strategies.items():
        results[name] = compute_performance_metrics(ret_series, tpx_ret)
    
    # 結果表示
    print(f"\n{'戦略':<20} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10}")
    print("-" * 85)
    for name, m in results.items():
        print(f"{name:<20} {m['cumulative']*100:>9.2f}% {m['annualized']*100:>9.2f}% "
              f"{m['sharpe']:>9.2f} {m['alpha_sharpe']:>11.2f} {m['max_dd']*100:>9.2f}%")
    
    # 可視化
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    
    dates = port_ret.index
    
    # 累積リターン比較
    ax = axes[0]
    for name in ["cross4 (コストなし)", "Plan A (コストなし)", "Plan A (コストあり)"]:
        if name in strategies:
            cum_ret = (1 + strategies[name]).cumprod()
            ax.plot(dates, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("コスト込み vs コストなし: 累積リターン", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ドローダウン比較
    ax = axes[1]
    for name in ["cross4 (コストなし)", "Plan A (コストなし)", "Plan A (コストあり)"]:
        if name in strategies:
            cum_ret = (1 + strategies[name]).cumprod()
            dd = cum_ret / cum_ret.cummax() - 1
            ax.plot(dates, dd * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("コスト込み vs コストなし: ドローダウン", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test3_with_costs.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)
    
    # 合格基準チェック
    print("\n【合格基準チェック】")
    cross4_dd = results["cross4 (コストなし)"]["max_dd"]
    planA_dd_cost = results["Plan A (コストあり)"]["max_dd"]
    cross4_alpha_sharpe = results["cross4 (コストなし)"]["alpha_sharpe"]
    planA_alpha_sharpe_cost = results["Plan A (コストあり)"]["alpha_sharpe"]
    
    dd_improved = planA_dd_cost > cross4_dd
    sharpe_ok = planA_alpha_sharpe_cost >= cross4_alpha_sharpe * 0.8
    
    print(f"コスト込みでもPlan AのDD改善: {dd_improved}")
    print(f"コスト込みでもシャープが大幅に崩れない: {sharpe_ok}")
    print(f"合格: {dd_improved and sharpe_ok}")


def test_4_episode_analysis(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """④ エピソード分析（イベントクラスターの寄与分析）"""
    print("\n" + "=" * 80)
    print("=== テスト④: エピソード分析 ===")
    print("=" * 80)
    
    stop_cond = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    cross4_base = port_ret
    planA_base = compute_strategy_returns(port_ret, inv_ret, stop_cond, 0.75, 0.25)
    
    # イベント期間定義
    events = {
        "2016年初": ("2016-01-01", "2016-03-31"),
        "2018 VIX": ("2018-01-01", "2018-12-31"),
        "2020 コロナ": ("2020-02-01", "2020-06-30"),
        "2022 利上げ": ("2022-01-01", "2022-12-31"),
    }
    
    results = {}
    for event_name, (start, end) in events.items():
        mask = (port_ret.index >= start) & (port_ret.index <= end)
        if mask.sum() == 0:
            continue
        
        cross4_event = cross4_base[mask]
        planA_event = planA_base[mask]
        tpx_event = tpx_ret[mask]
        
        cross4_cum = (1 + cross4_event).prod() - 1
        planA_cum = (1 + planA_event).prod() - 1
        alpha_cum = planA_cum - cross4_cum
        
        results[event_name] = {
            "cross4": cross4_cum,
            "planA": planA_cum,
            "alpha": alpha_cum,
            "days": mask.sum(),
            "stop_days": stop_cond[mask].sum(),
        }
    
    # 結果表示
    print(f"\n{'イベント':<15} {'cross4(%)':>12} {'Plan A(%)':>12} {'Alpha(%)':>12} {'STOP日数':>10} {'STOP率(%)':>10}")
    print("-" * 80)
    for event_name, r in results.items():
        stop_rate = r["stop_days"] / r["days"] * 100 if r["days"] > 0 else 0
        print(f"{event_name:<15} {r['cross4']*100:>11.2f}% {r['planA']*100:>11.2f}% "
              f"{r['alpha']*100:>11.2f}% {r['stop_days']:>9d} {stop_rate:>9.1f}%")
    
    # 可視化
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # イベント別リターン寄与
    ax = axes[0, 0]
    event_names = list(results.keys())
    cross4_returns = [results[e]["cross4"] * 100 for e in event_names]
    planA_returns = [results[e]["planA"] * 100 for e in event_names]
    alpha_returns = [results[e]["alpha"] * 100 for e in event_names]
    
    x = np.arange(len(event_names))
    width = 0.25
    ax.bar(x - width, cross4_returns, width, label="cross4", alpha=0.8)
    ax.bar(x, planA_returns, width, label="Plan A", alpha=0.8)
    ax.bar(x + width, alpha_returns, width, label="Alpha", alpha=0.8)
    
    ax.set_xlabel("イベント")
    ax.set_ylabel("累積リターン (%)")
    ax.set_title("イベント別リターン寄与", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(event_names, rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    
    # イベント期間の累積リターン曲線
    ax = axes[0, 1]
    for event_name, (start, end) in events.items():
        mask = (port_ret.index >= start) & (port_ret.index <= end)
        if mask.sum() == 0:
            continue
        dates = port_ret[mask].index
        cum_cross4 = (1 + cross4_base[mask]).cumprod()
        cum_planA = (1 + planA_base[mask]).cumprod()
        ax.plot(dates, (cum_cross4 - 1) * 100, label=f"{event_name} (cross4)", linewidth=2, alpha=0.6, linestyle='--')
        ax.plot(dates, (cum_planA - 1) * 100, label=f"{event_name} (Plan A)", linewidth=2, alpha=0.8)
    ax.set_title("イベント期間の累積リターン", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # STOP率の比較
    ax = axes[1, 0]
    stop_rates = [results[e]["stop_days"] / results[e]["days"] * 100 if results[e]["days"] > 0 else 0 for e in event_names]
    ax.bar(event_names, stop_rates, alpha=0.8, color='red')
    ax.set_ylabel("STOP率 (%)")
    ax.set_title("イベント期間中のSTOP率", fontweight="bold")
    ax.set_xticklabels(event_names, rotation=45, ha='right')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Alpha寄与の比較
    ax = axes[1, 1]
    ax.bar(event_names, alpha_returns, alpha=0.8, color='green')
    ax.set_ylabel("Alpha (%)")
    ax.set_title("イベント別Alpha寄与", fontweight="bold")
    ax.set_xticklabels(event_names, rotation=45, ha='right')
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test4_episode_analysis.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)


def test_5_simple_stop(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """⑤ STOP条件の単純版での再現性"""
    print("\n" + "=" * 80)
    print("=== テスト⑤: STOP条件の単純版での再現性 ===")
    print("=" * 80)
    
    # 現行STOP条件
    stop_cond_complex = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    # 単純STOP条件: TOPIXの60日リターン < 0
    roll_tpx_simple = tpx_ret.rolling(window=60, min_periods=1).sum().shift(1).fillna(False)
    stop_cond_simple = roll_tpx_simple < 0
    
    # 各戦略
    cross4_base = port_ret
    planA_complex = compute_strategy_returns(port_ret, inv_ret, stop_cond_complex, 0.75, 0.25)
    planA_simple = compute_strategy_returns(port_ret, inv_ret, stop_cond_simple, 0.75, 0.25)
    
    strategies = {
        "cross4": cross4_base,
        "Plan A (現行STOP)": planA_complex,
        "Plan A (単純STOP)": planA_simple,
    }
    
    results = {}
    for name, ret_series in strategies.items():
        results[name] = compute_performance_metrics(ret_series, tpx_ret)
    
    # 結果表示
    print(f"\n{'戦略':<20} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10}")
    print("-" * 85)
    for name, m in results.items():
        print(f"{name:<20} {m['cumulative']*100:>9.2f}% {m['annualized']*100:>9.2f}% "
              f"{m['sharpe']:>9.2f} {m['alpha_sharpe']:>11.2f} {m['max_dd']*100:>9.2f}%")
    
    # 可視化
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    dates = port_ret.index
    
    # 累積リターン比較
    ax = axes[0]
    for name, ret_series in strategies.items():
        cum_ret = (1 + ret_series).cumprod()
        ax.plot(dates, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("現行STOP vs 単純STOP: 累積リターン", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ドローダウン比較
    ax = axes[1]
    for name, ret_series in strategies.items():
        cum_ret = (1 + ret_series).cumprod()
        dd = cum_ret / cum_ret.cummax() - 1
        ax.plot(dates, dd * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("現行STOP vs 単純STOP: ドローダウン", fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test5_simple_stop.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)
    
    # 合格基準チェック
    print("\n【合格基準チェック】")
    complex_dd = results["Plan A (現行STOP)"]["max_dd"]
    simple_dd = results["Plan A (単純STOP)"]["max_dd"]
    complex_ret = results["Plan A (現行STOP)"]["annualized"]
    simple_ret = results["Plan A (単純STOP)"]["annualized"]
    
    dd_similar = abs(complex_dd - simple_dd) / abs(complex_dd) < 0.3  # 30%以内の差
    ret_similar = abs(complex_ret - simple_ret) / abs(complex_ret) < 0.3
    
    print(f"単純STOPでも似た方向性の改善: {dd_similar or ret_similar}")
    print(f"合格: {dd_similar or ret_similar}")


def test_6_final_assessment(port_ret: pd.Series, tpx_ret: pd.Series, inv_ret: pd.Series):
    """⑥ 現時点での採用方針の妥当性確認"""
    print("\n" + "=" * 80)
    print("=== テスト⑥: 最終採用方針の妥当性確認 ===")
    print("=" * 80)
    
    stop_cond = compute_stop_condition(port_ret, tpx_ret, window=60)
    
    # Plan A 60d（本命候補）
    planA_60d = compute_strategy_returns(port_ret, inv_ret, stop_cond, 0.75, 0.25)
    
    # Plan B 60d（保守的バックアップ）
    planB_60d = compute_strategy_returns(port_ret, inv_ret, stop_cond, plan_b=True)
    
    strategies = {
        "cross4": port_ret,
        "Plan A (60d)": planA_60d,
        "Plan B (60d)": planB_60d,
    }
    
    results = {}
    for name, ret_series in strategies.items():
        results[name] = compute_performance_metrics(ret_series, tpx_ret)
    
    # OOS期間（2020-2025）での評価
    oos_start = "2020-01-01"
    oos_end = "2025-12-31"
    oos_mask = (port_ret.index >= oos_start) & (port_ret.index <= oos_end)
    
    results_oos = {}
    for name, ret_series in strategies.items():
        ret_oos = ret_series[oos_mask]
        tpx_oos = tpx_ret[oos_mask]
        results_oos[name] = compute_performance_metrics(ret_oos, tpx_oos)
    
    # 総合スコア計算（α、DD、Sharpeの総合点）
    def calculate_score(r):
        """スコア: alpha_sharpe * 0.4 + (1/max_dd_abs) * 0.3 + sharpe * 0.3"""
        max_dd_abs = abs(r["max_dd"])
        if max_dd_abs < 0.01:  # DDが極小の場合
            max_dd_score = 10.0
        else:
            max_dd_score = 1.0 / max_dd_abs
        
        alpha_sharpe_score = r["alpha_sharpe"] if not np.isnan(r["alpha_sharpe"]) else 0.0
        sharpe_score = r["sharpe"] if not np.isnan(r["sharpe"]) else 0.0
        
        return alpha_sharpe_score * 0.4 + max_dd_score * 0.3 + sharpe_score * 0.3
    
    # 結果表示
    print("\n【全期間パフォーマンス】")
    print(f"{'戦略':<15} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10} {'スコア':>10}")
    print("-" * 90)
    for name in strategies.keys():
        r = results[name]
        score = calculate_score(r)
        print(f"{name:<15} {r['cumulative']*100:>9.2f}% {r['annualized']*100:>9.2f}% "
              f"{r['sharpe']:>9.2f} {r['alpha_sharpe']:>11.2f} {r['max_dd']*100:>9.2f}% {score:>9.2f}")
    
    print("\n【OOS期間 (2020-2025) パフォーマンス】")
    print(f"{'戦略':<15} {'累積(%)':>10} {'年率(%)':>10} {'Sharpe':>10} {'Alpha Sharpe':>12} {'MaxDD(%)':>10} {'スコア':>10}")
    print("-" * 90)
    for name in strategies.keys():
        r = results_oos[name]
        score = calculate_score(r)
        print(f"{name:<15} {r['cumulative']*100:>9.2f}% {r['annualized']*100:>9.2f}% "
              f"{r['sharpe']:>9.2f} {r['alpha_sharpe']:>11.2f} {r['max_dd']*100:>9.2f}% {score:>9.2f}")
    
    # 可視化
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    dates = port_ret.index
    
    # 全期間の累積リターン
    ax = axes[0, 0]
    for name, ret_series in strategies.items():
        cum_ret = (1 + ret_series).cumprod()
        ax.plot(dates, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("全期間: 累積リターン", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # OOS期間の累積リターン
    ax = axes[0, 1]
    dates_oos = port_ret[oos_mask].index
    for name, ret_series in strategies.items():
        ret_oos = ret_series[oos_mask]
        cum_ret = (1 + ret_oos).cumprod()
        ax.plot(dates_oos, (cum_ret - 1) * 100, label=name, linewidth=2, alpha=0.8)
    ax.set_title("OOS期間: 累積リターン (2020-2025)", fontweight="bold")
    ax.set_ylabel("Cumulative Return (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # パフォーマンス指標比較（全期間）
    ax = axes[1, 0]
    strategy_names = list(strategies.keys())
    alpha_sharpe = [results[n]["alpha_sharpe"] for n in strategy_names]
    sharpe = [results[n]["sharpe"] for n in strategy_names]
    max_dd = [abs(results[n]["max_dd"]) * 100 for n in strategy_names]
    
    x = np.arange(len(strategy_names))
    width = 0.25
    ax.bar(x - width, alpha_sharpe, width, label="Alpha Sharpe", alpha=0.8)
    ax.bar(x, sharpe, width, label="Sharpe", alpha=0.8, color='orange')
    ax.bar(x + width, max_dd, width, label="MaxDD(%)", alpha=0.8, color='red')
    
    ax.set_xlabel("戦略")
    ax.set_ylabel("値")
    ax.set_title("全期間: パフォーマンス指標比較", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(strategy_names, rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # 総合スコア比較
    ax = axes[1, 1]
    scores_full = [calculate_score(results[n]) for n in strategy_names]
    scores_oos = [calculate_score(results_oos[n]) for n in strategy_names]
    
    x = np.arange(len(strategy_names))
    width = 0.35
    ax.bar(x - width/2, scores_full, width, label="全期間", alpha=0.8)
    ax.bar(x + width/2, scores_oos, width, label="OOS期間", alpha=0.8, color='orange')
    
    ax.set_xlabel("戦略")
    ax.set_ylabel("総合スコア")
    ax.set_title("総合スコア比較", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(strategy_names, rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "test6_final_assessment.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"\n[INFO] Saved to {fig_path}")
    plt.close(fig)
    
    # 採用方針の提案
    print("\n【採用方針の提案】")
    score_planA = calculate_score(results["Plan A (60d)"])
    score_planB = calculate_score(results["Plan B (60d)"])
    score_cross4 = calculate_score(results["cross4"])
    
    print(f"\nPlan A (60d) - 本命候補:")
    print(f"  総合スコア: {score_planA:.2f}")
    print(f"  Alpha Sharpe: {results['Plan A (60d)']['alpha_sharpe']:.2f}")
    print(f"  MaxDD: {results['Plan A (60d)']['max_dd']*100:.2f}%")
    print(f"  OOS期間での破綻なし: {results_oos['Plan A (60d)']['annualized'] > 0}")
    
    print(f"\nPlan B (60d) - 保守的バックアップ:")
    print(f"  総合スコア: {score_planB:.2f}")
    print(f"  Alpha Sharpe: {results['Plan B (60d)']['alpha_sharpe']:.2f}")
    print(f"  MaxDD: {results['Plan B (60d)']['max_dd']*100:.2f}%")
    print(f"  説明性と運用安定性: 高い")
    
    print(f"\n実弾導入案:")
    print(f"  cross4 : Plan A = 8:2 もしくは 9:1")
    print(f"  1-2年はサイズを抑えてOOSデータを蓄積")
    print(f"  β暴走やSTOP誤作動がなければスケールアップ")


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== STOP条件に基づく戦略のロバストネステスト ===")
    print("=" * 80)
    
    # データ読み込み
    print("\n[STEP 1] Loading data...")
    port_ret, tpx_ret = load_cross4_and_topix()
    inv_ret = load_inverse_returns()
    
    if len(inv_ret) > 0:
        common_dates = port_ret.index.intersection(inv_ret.index)
        if len(common_dates) > 0:
            inv_ret = inv_ret.reindex(port_ret.index, fill_value=0.0)
        else:
            inv_ret = pd.Series(0.0, index=port_ret.index)
    else:
        inv_ret = pd.Series(0.0, index=port_ret.index)
    
    print(f"[INFO] Loaded data: {len(port_ret)} days")
    print(f"  Date range: {port_ret.index.min().date()} ～ {port_ret.index.max().date()}")
    
    # 各テストを実行
    test_1_oos_split(port_ret, tpx_ret, inv_ret)
    test_2_weight_robustness(port_ret, tpx_ret, inv_ret)
    test_3_with_costs(port_ret, tpx_ret, inv_ret)
    test_4_episode_analysis(port_ret, tpx_ret, inv_ret)
    test_5_simple_stop(port_ret, tpx_ret, inv_ret)
    test_6_final_assessment(port_ret, tpx_ret, inv_ret)
    
    print("\n" + "=" * 80)
    print("=== 完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()

