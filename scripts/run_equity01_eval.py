"""
統合評価スクリプト（完全統合型ダッシュボード）

このスクリプトを実行すると、以下が順番に実行されます：
- 単体版（baseline, H=1）
- ホライゾン別（H=5, 10, 20, 60）
- アンサンブル版
- 月次・年次サマリ
- rolling α

使い方:
    python scripts/run_equity01_eval.py
    python scripts/run_equity01_eval.py --horizon-ensemble

【運用ルール】
- 基本は run_equity01_eval.py 以外から実行しない運用ルールにする
- 単体テスト以外は、評価も分析も全部 run_equity01_eval.py 経由で実行
- 手計算したくなったときも、まず run_equity01_eval.py を実行してから Parquet を読む
- これにより、TOPIXデータの更新漏れや日付不整合を防げる
"""
import argparse
from pathlib import Path
import os
import sys
from typing import List, Dict

import numpy as np
import pandas as pd

# scripts ディレクトリをパスに追加
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_index_tpx_daily import main as build_index_main
from calc_alpha_beta import main as calc_alpha_main
from monthly_performance import compute_monthly_performance
from horizon_ensemble import run_horizon_ensemble

WINDOWS = [10, 20, 60, 120]


def print_header(horizons: List[int] = None) -> None:
    """環境・パラメータ表示"""
    print("=" * 60)
    print("=== equity01 統合評価ダッシュボード ===")
    print("=" * 60)
    if horizons:
        print(f"Horizons: {horizons}")
    print()


def compute_rolling_relative_alpha(df_alpha: pd.DataFrame, label: str = "") -> pd.DataFrame:
    """
    moving window 相対αを計算（DataFrame版）
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date").reset_index(drop=True)
    
    if not {"port_ret_cc", "tpx_ret_cc"}.issubset(df.columns):
        raise KeyError(
            f"必要な列 'port_ret_cc', 'tpx_ret_cc' が見つかりません: {df.columns.tolist()}"
        )
    
    port = df["port_ret_cc"].astype(float)
    tpx = df["tpx_ret_cc"].astype(float)
    
    out = df[["trade_date"]].copy()
    
    for w in WINDOWS:
        port_cum = (1.0 + port).rolling(w, min_periods=1).apply(np.prod, raw=True)
        tpx_cum = (1.0 + tpx).rolling(w, min_periods=1).apply(np.prod, raw=True)
        
        out[f"port_cum_{w}d"] = port_cum
        out[f"tpx_cum_{w}d"] = tpx_cum
        out[f"rel_alpha_{w}d"] = port_cum - tpx_cum
    
    if label:
        out_path = Path(f"data/processed/rolling_relative_alpha_{label}.parquet")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path, index=False)
    
    return out


def print_baseline_summary(df_alpha: pd.DataFrame) -> None:
    """Baseline（H=1）のサマリを表示"""
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    print("\n=== Baseline (H=1, Daily Rebalance) ===")
    print(f"Total Port: {total_port:+.2%}")
    print(f"Total TOPIX: {total_tpx:+.2%}")
    print(f"Total Alpha: {total_alpha:+.2%}")
    print(f"Sharpe(α): {sharpe_alpha:.2f}")
    print(f"期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"日数: {len(df)}")


def print_horizon_summary(summary: Dict) -> None:
    """ホライゾン別サマリを表示"""
    print(
        f"[H{summary['horizon']}] "
        f"total_port={summary['total_port']:+.2%}  "
        f"total_alpha={summary['total_alpha']:+.2%}  "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}  "
        f"max_dd={summary['max_drawdown']:+.2%}"
    )


def print_ensemble_summary(df_ens_alpha: pd.DataFrame) -> None:
    """アンサンブル版のサマリを表示"""
    df = df_ens_alpha.copy()
    df = df.sort_values("trade_date")
    
    # 列名を確認（port_ret_cc_ens または port_ret_cc）
    port_col = "port_ret_cc_ens" if "port_ret_cc_ens" in df.columns else "port_ret_cc"
    alpha_col = "rel_alpha_ens" if "rel_alpha_ens" in df.columns else "rel_alpha_daily"
    
    total_port = (1 + df[port_col]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    mean_alpha = df[alpha_col].mean()
    std_alpha = df[alpha_col].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    print("\n=== Ensemble (Equal Weight) ===")
    print(f"Total Port: {total_port:+.2%}")
    print(f"Total TOPIX: {total_tpx:+.2%}")
    print(f"Total Alpha: {total_alpha:+.2%}")
    print(f"Sharpe(α): {sharpe_alpha:.2f}")
    print(f"期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"日数: {len(df)}")


def print_monthly_comparison(
    baseline_monthly: pd.DataFrame,
    horizon_monthlies: Dict[int, pd.DataFrame],
    ensemble_monthly: pd.DataFrame,
) -> None:
    """月次相対αを比較表示"""
    print("\n=== Monthly Relative Alpha Comparison ===")
    
    # 年×月のキーでマージ
    all_data = []
    
    # Baseline
    baseline_monthly = baseline_monthly.copy()
    baseline_monthly["key"] = baseline_monthly["year"].astype(str) + "-" + baseline_monthly["month"].astype(str).str.zfill(2)
    all_data.append(("Baseline", baseline_monthly[["key", "rel_alpha"]].rename(columns={"rel_alpha": "Baseline"})))
    
    # Horizons
    for h, df_m in horizon_monthlies.items():
        df_m = df_m.copy()
        df_m["key"] = df_m["year"].astype(str) + "-" + df_m["month"].astype(str).str.zfill(2)
        all_data.append((f"H{h}", df_m[["key", "rel_alpha"]].rename(columns={"rel_alpha": f"H{h}"})))
    
    # Ensemble
    ensemble_monthly = ensemble_monthly.copy()
    ensemble_monthly["key"] = ensemble_monthly["year"].astype(str) + "-" + ensemble_monthly["month"].astype(str).str.zfill(2)
    all_data.append(("Ensemble", ensemble_monthly[["key", "rel_alpha"]].rename(columns={"rel_alpha": "Ensemble"})))
    
    # マージ
    from functools import reduce
    df_merged = reduce(
        lambda l, r: pd.merge(l, r, on="key", how="outer"),
        [df for _, df in all_data]
    )
    df_merged = df_merged.sort_values("key")
    
    # 表示（最近12ヶ月分）
    print(df_merged.tail(12).to_string(index=False, float_format="{:+.2%}".format))


def print_rolling_alpha_comparison(
    baseline_rolling: pd.DataFrame,
    ensemble_rolling: pd.DataFrame,
) -> None:
    """Rolling αを比較表示"""
    print("\n=== Rolling Alpha Comparison (120d) ===")
    
    if "rel_alpha_120d" in baseline_rolling.columns and "rel_alpha_120d" in ensemble_rolling.columns:
        baseline_mean = baseline_rolling["rel_alpha_120d"].dropna().mean()
        ensemble_mean = ensemble_rolling["rel_alpha_120d"].dropna().mean()
        
        print(f"Baseline: {baseline_mean:+.6f}")
        print(f"Ensemble: {ensemble_mean:+.6f}")
        print(f"改善: {(ensemble_mean - baseline_mean):+.6f}")
    else:
        print("⚠ Rolling alpha (120d) のデータが不足しています")


def run_integrated_eval(horizons: List[int] = [5, 10, 20, 60]) -> None:
    """
    完全統合型評価パイプライン
    """
    print_header(horizons)
    
    # === STEP 1: TOPIX index update ===
    print("=== STEP 1: TOPIX Index Update ===")
    try:
        build_index_main()
        print("✓ TOPIXリターン更新完了")
    except Exception as e:
        print(f"✗ TOPIXリターン更新失敗: {e}")
        raise
    
    # === STEP 2: load shared features & prices ===
    print("\n=== STEP 2: Load Shared Features & Prices ===")
    features, prices = build_features_shared()
    print(f"✓ Features: {len(features)} rows")
    print(f"✓ Prices: {len(prices)} rows")
    
    # === STEP 3: baseline backtest (H=1) ===
    print("\n=== STEP 3: Baseline Backtest (H=1) ===")
    baseline_pt = backtest_with_horizon(features, prices, holding_horizon=1)
    baseline_alpha = calc_alpha_beta_for_horizon(baseline_pt, horizon=1)
    print_baseline_summary(baseline_alpha)
    
    # 保存
    baseline_pt_path = Path("data/processed/paper_trade_baseline.parquet")
    baseline_pt_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_pt.to_parquet(baseline_pt_path, index=False)
    
    baseline_alpha_path = Path("data/processed/paper_trade_with_alpha_beta_baseline.parquet")
    baseline_alpha.to_parquet(baseline_alpha_path, index=False)
    
    # === STEP 4: horizon-specific backtest ===
    print("\n=== STEP 4: Horizon-Specific Backtest ===")
    summaries = []
    horizon_alphas = {}
    horizon_monthlies = {}
    
    for h in horizons:
        print(f"\n[H{h}] バックテスト実行中...")
        try:
            df_pt_h = backtest_with_horizon(features, prices, h)
            df_alpha_h = calc_alpha_beta_for_horizon(df_pt_h, h)
            summary = summarize_horizon(df_alpha_h, h)
            summaries.append(summary)
            print_horizon_summary(summary)
            horizon_alphas[h] = df_alpha_h
            
            # 月次集計
            monthly, yearly = compute_monthly_perf(
                df_alpha_h,
                label=f"h{h}",
                out_prefix="data/processed/horizon"
            )
            horizon_monthlies[h] = monthly
            
        except Exception as e:
            print(f"  [H{h}] エラー: {e}")
            raise
    
    # ホライゾン別サマリを保存
    if summaries:
        df_summary = pd.DataFrame(summaries)
        summary_path = Path("data/processed/horizon_perf_summary.parquet")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        df_summary.to_parquet(summary_path, index=False)
        
        print("\n=== Horizon Performance Summary ===")
        display_cols = ["horizon", "days", "total_port", "total_tpx", "total_alpha", 
                       "alpha_sharpe_annual", "max_drawdown"]
        display_df = df_summary[display_cols].copy()
        for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
        print(display_df.to_string(index=False))
    
    # === STEP 5: ensemble ===
    print("\n=== STEP 5: Ensemble (Equal Weight) ===")
    df_ens = ensemble_horizons(horizons)
    
    # アンサンブル版の相対αを計算
    # TOPIXデータを読み込み
    tpx_path = Path("data/processed/index_tpx_daily.parquet")
    df_tpx = pd.read_parquet(tpx_path)
    df_tpx = df_tpx.sort_values("trade_date").reset_index(drop=True)
    
    # マージ
    df_ens["trade_date"] = pd.to_datetime(df_ens["trade_date"])
    df_ens_alpha = df_ens.merge(
        df_tpx[["trade_date", "tpx_ret_cc"]],
        on="trade_date",
        how="inner"
    )
    
    # 相対αを計算
    df_ens_alpha["rel_alpha_daily"] = df_ens_alpha["port_ret_cc_ens"] - df_ens_alpha["tpx_ret_cc"]
    df_ens_alpha["cum_port"] = (1.0 + df_ens_alpha["port_ret_cc_ens"]).cumprod()
    df_ens_alpha["cum_tpx"] = (1.0 + df_ens_alpha["tpx_ret_cc"]).cumprod()
    
    # 保存
    ens_alpha_path = Path("data/processed/paper_trade_with_alpha_beta_ensemble.parquet")
    ens_alpha_path.parent.mkdir(parents=True, exist_ok=True)
    df_ens_alpha.to_parquet(ens_alpha_path, index=False)
    
    print_ensemble_summary(df_ens_alpha)
    
    # アンサンブル版の月次集計（列名を調整）
    df_ens_alpha_for_monthly = df_ens_alpha.copy()
    if "port_ret_cc_ens" in df_ens_alpha_for_monthly.columns:
        df_ens_alpha_for_monthly["port_ret_cc"] = df_ens_alpha_for_monthly["port_ret_cc_ens"]
    ensemble_monthly, ensemble_yearly = compute_monthly_perf(
        df_ens_alpha_for_monthly,
        label="ensemble",
        out_prefix="data/processed/horizon"
    )
    
    # === STEP 6: monthly/yearly comparison ===
    print("\n=== STEP 6: Monthly/Yearly Comparison ===")
    baseline_monthly, baseline_yearly = compute_monthly_perf(
        baseline_alpha,
        label="baseline",
        out_prefix="data/processed"
    )
    
    print_monthly_comparison(
        baseline_monthly,
        horizon_monthlies,
        ensemble_monthly
    )
    
    # === STEP 7: rolling alpha comparison ===
    print("\n=== STEP 7: Rolling Alpha Comparison ===")
    try:
        baseline_rolling = compute_rolling_relative_alpha(baseline_alpha, label="baseline")
        # アンサンブル版の列名を調整
        df_ens_alpha_for_rolling = df_ens_alpha.copy()
        if "port_ret_cc_ens" in df_ens_alpha_for_rolling.columns:
            df_ens_alpha_for_rolling["port_ret_cc"] = df_ens_alpha_for_rolling["port_ret_cc_ens"]
        ensemble_rolling = compute_rolling_relative_alpha(df_ens_alpha_for_rolling, label="ensemble")
        
        print_rolling_alpha_comparison(baseline_rolling, ensemble_rolling)
    except Exception as e:
        print(f"⚠ Rolling alpha計算でエラー: {e}")
    
    print("\n" + "=" * 60)
    print("=== 全処理完了 ===")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="equity01 統合評価パイプライン")
    parser.add_argument(
        "--horizon-ensemble",
        action="store_true",
        help="ホライゾンアンサンブルを含む完全統合評価を実行する",
    )
    args = parser.parse_args()
    
    # ホライゾンアンサンブルモード（完全統合版）
    if args.horizon_ensemble:
        run_integrated_eval(horizons=[5, 10, 20, 60])
        return
    
    # 通常の評価パイプライン（従来版）
    print("=" * 60)
    print("equity01 評価パイプライン実行")
    print("=" * 60)
    
    print("\n=== STEP 1: build_index_tpx_daily ===")
    try:
        build_index_main()
        print("✓ TOPIXリターン更新完了")
    except Exception as e:
        print(f"✗ TOPIXリターン更新失敗: {e}")
        raise
    
    print("\n=== STEP 2: calc_alpha_beta ===")
    try:
        calc_alpha_main()
        print("✓ ペーパートレード + 相対α計算完了")
    except Exception as e:
        print(f"✗ ペーパートレード + 相対α計算失敗: {e}")
        raise
    
    print("\n=== STEP 3: rolling_relative_alpha ===")
    try:
        # 通常モード用のrolling alpha計算
        src = Path("data/processed/paper_trade_with_alpha_beta.parquet")
        if src.exists():
            df_alpha = pd.read_parquet(src)
            compute_rolling_relative_alpha(df_alpha, label="")
            print("✓ moving window 相対α計算完了")
        else:
            print("⚠ paper_trade_with_alpha_beta.parquet が見つかりません。スキップします。")
    except Exception as e:
        print(f"✗ moving window 相対α計算失敗: {e}")
        raise
    
    print("\n=== STEP 4: monthly_performance ===")
    try:
        compute_monthly_performance()
        print("✓ 月次・年次パフォーマンス集計完了")
    except Exception as e:
        print(f"✗ 月次・年次パフォーマンス集計失敗: {e}")
        raise
    
    print("\n=== STEP 5: horizon_ensemble ===")
    try:
        run_horizon_ensemble(horizons=[1, 5, 10, 20, 60])
        print("✓ ホライゾンアンサンブル完了")
    except Exception as e:
        print(f"✗ ホライゾンアンサンブル失敗: {e}")
        raise
    
    print("\n" + "=" * 60)
    print("全ての処理が完了しました！")
    print("=" * 60)


if __name__ == "__main__":
    main()
