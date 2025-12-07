#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
動的ウェイト配分ポートフォリオの年次・月次パフォーマンスと相対アルファを計算

他のensembleシリーズと同様のフォーマットで出力します。
"""

import sys
from pathlib import Path
from typing import Tuple

import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# horizon_ensemble.pyのcompute_monthly_perfをインポート
from horizon_ensemble import compute_monthly_perf, print_horizon_performance


def load_tpx_returns() -> pd.DataFrame:
    """TOPIX日次リターンを読み込む"""
    tpx_path = Path("data/processed/index_tpx_daily.parquet")
    if not tpx_path.exists():
        raise FileNotFoundError(
            f"{tpx_path} がありません。先に build_index_tpx_daily.py を実行してください。"
        )
    
    df_tpx = pd.read_parquet(tpx_path)
    df_tpx = df_tpx.sort_values("trade_date").reset_index(drop=True)
    return df_tpx[["trade_date", "tpx_ret_cc"]]


def compute_alpha_for_dynamic_portfolio(
    portfolio_path: Path,
    method_name: str,
) -> pd.DataFrame:
    """
    動的ポートフォリオの相対αを計算
    
    Parameters
    ----------
    portfolio_path : Path
        ポートフォリオファイルのパス（portfolio_root_sigma.parquet または portfolio_sigma.parquet）
    method_name : str
        メソッド名（"sqrt_sigma" または "sigma"）
    
    Returns
    -------
    pd.DataFrame
        相対αを含むDataFrame
    """
    # ポートフォリオデータを読み込む
    df_port = pd.read_parquet(portfolio_path)
    
    # 日付カラム名を統一
    date_col = "date" if "date" in df_port.columns else "trade_date"
    if date_col not in df_port.columns:
        raise KeyError(f"日付カラムが見つかりません: {df_port.columns.tolist()}")
    
    # 日付カラムを統一
    if "trade_date" not in df_port.columns:
        if "date" in df_port.columns:
            df_port = df_port.rename(columns={"date": "trade_date"})
        else:
            raise KeyError(f"日付カラムが見つかりません: {df_port.columns.tolist()}")
    
    df_port["trade_date"] = pd.to_datetime(df_port["trade_date"])
    df_port = df_port.sort_values("trade_date").reset_index(drop=True)
    
    # リターンカラム名を確認
    ret_col = None
    for col in ["combined_ret_sqrt", "combined_ret_sigma", "port_ret_cc"]:
        if col in df_port.columns:
            ret_col = col
            break
    
    if ret_col is None:
        raise KeyError(f"リターンカラムが見つかりません: {df_port.columns.tolist()}")
    
    df_port = df_port.rename(columns={ret_col: "port_ret_cc"})
    
    # TOPIXデータを読み込んでマージ
    df_tpx = load_tpx_returns()
    df = df_port.merge(df_tpx, on="trade_date", how="inner")
    df = df.sort_values("trade_date").reset_index(drop=True)
    
    # 相対αを計算
    df["rel_alpha_daily"] = df["port_ret_cc"] - df["tpx_ret_cc"]
    df["cum_port"] = (1.0 + df["port_ret_cc"]).cumprod()
    df["cum_tpx"] = (1.0 + df["tpx_ret_cc"]).cumprod()
    
    # 保存
    output_path = Path(f"data/processed/dynamic_portfolio_with_alpha_beta_{method_name}.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    
    print(f"[INFO] Saved alpha-beta data to {output_path}")
    
    return df


def compute_performance_for_dynamic_portfolio(
    method_name: str = "sqrt_sigma",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    動的ポートフォリオの月次・年次パフォーマンスを計算
    
    Parameters
    ----------
    method_name : str
        メソッド名（"sqrt_sigma" または "sigma"）
    
    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        (monthly_returns, yearly_returns) のタプル
    """
    # ポートフォリオファイルのパスを決定
    if method_name == "sqrt_sigma":
        portfolio_path = Path("data/processed/portfolio_root_sigma.parquet")
    elif method_name == "sigma":
        portfolio_path = Path("data/processed/portfolio_sigma.parquet")
    else:
        raise ValueError(f"Unknown method: {method_name}")
    
    if not portfolio_path.exists():
        raise FileNotFoundError(
            f"{portfolio_path} がありません。先に build_dynamic_portfolio.py を実行してください。"
        )
    
    print(f"\n[STEP 1] Loading portfolio data from {portfolio_path}...")
    df_alpha = compute_alpha_for_dynamic_portfolio(portfolio_path, method_name)
    
    print(f"[STEP 2] Computing monthly and yearly performance...")
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=f"dynamic_{method_name}",
        out_prefix="data/processed/dynamic_portfolio"
    )
    
    return monthly, yearly, df_alpha


def print_dynamic_portfolio_performance(
    df_alpha: pd.DataFrame,
    method_name: str,
    monthly_returns: pd.DataFrame,
    yearly: pd.DataFrame,
) -> None:
    """
    動的ポートフォリオのパフォーマンスを表示
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    # 累積パフォーマンス
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    # 日次統計
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    # ドローダウン
    cum_port = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cum_port.cummax()
    drawdown = (cum_port / rolling_max - 1.0).min()
    
    # タイトル
    print(f"\n=== Dynamic Portfolio Performance ({method_name}) ===")
    
    print(f"累積: Port {total_port:+.2%}, TOPIX {total_tpx:+.2%}, α {total_alpha:+.2%}")
    print(f"Sharpe(α): {sharpe_alpha:.2f}")
    print(f"maxDD: {drawdown:+.2%}")
    print(f"期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"日数: {len(df)}")
    
    # 月次リターン表
    print("\n【月次リターン（相対α）】")
    try:
        pivot_monthly = monthly_returns.pivot_table(
            index="year", columns="month", values="rel_alpha", aggfunc="first"
        )
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        # 列名を月名に変換
        new_cols = {}
        for col in pivot_monthly.columns:
            if isinstance(col, int) and 1 <= col <= 12:
                new_cols[col] = month_names[col - 1]
        pivot_monthly = pivot_monthly.rename(columns=new_cols)
        
        # 年間列を追加
        yearly_indexed = yearly.set_index("year")["rel_alpha"]
        pivot_monthly["年間"] = yearly_indexed
        
        print(pivot_monthly.to_string(float_format="{:+.2%}".format))
    except Exception as e:
        print(f"⚠ 月次リターン表の生成でエラー: {e}")
        print(monthly_returns[["year", "month", "port_return", "tpx_return", "rel_alpha"]].to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次リターン表
    print("\n【年次リターン】")
    yearly_display = yearly[["year", "port_return", "tpx_return", "rel_alpha"]].copy()
    print(yearly_display.to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次統計
    print("\n【年次統計】")
    yearly_port_mean = yearly["port_return"].mean()
    yearly_tpx_mean = yearly["tpx_return"].mean()
    yearly_alpha_mean = yearly["rel_alpha"].mean()
    yearly_alpha_std = yearly["rel_alpha"].std()
    yearly_alpha_sharpe = yearly_alpha_mean / yearly_alpha_std if yearly_alpha_std > 0 else float("nan")
    yearly_win_rate = (yearly["rel_alpha"] > 0).mean()
    
    print(f"年率平均（Port）: {yearly_port_mean:+.4%}")
    print(f"年率平均（TOPIX）: {yearly_tpx_mean:+.4%}")
    print(f"年率平均（α）: {yearly_alpha_mean:+.4%}")
    print(f"年率標準偏差（α）: {yearly_alpha_std:+.4%}")
    print(f"年率αシャープ: {yearly_alpha_sharpe:+.4f}")
    print(f"年間勝率: {yearly_win_rate:+.2%}")


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== 動的ポートフォリオ 年次・月次パフォーマンス計算 ===")
    print("=" * 80)
    
    method_name = "sqrt_sigma"
    
    print(f"\n{'=' * 80}")
    print(f"=== {method_name.upper()} メソッド ===")
    print(f"{'=' * 80}")
    
    try:
        monthly, yearly, df_alpha = compute_performance_for_dynamic_portfolio(method_name)
        print_dynamic_portfolio_performance(df_alpha, method_name, monthly, yearly)
    except FileNotFoundError as e:
        print(f"[ERROR] {method_name}: {e}")
    except Exception as e:
        print(f"[ERROR] {method_name}: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("=== 完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()

