"""
統合評価レポート生成スクリプト（analysis側）

core/run_equity01_eval.py で生成された成果物を読み込み、
月次集計・ホライゾン分析・アンサンブル評価などの詳細分析を実行します。

設計ルール:
- core → analysis 依存は禁止
- core の成果物（parquet）を読み込んで分析する
- 出力は research/reports/（git管理外）

使い方:
    python scripts/analysis/run_eval_report.py
    python scripts/analysis/run_eval_report.py --horizon-ensemble
"""
import argparse
from pathlib import Path
import sys
from typing import Optional

import pandas as pd
import numpy as np

# scripts ディレクトリをパスに追加
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analysis.monthly_performance import compute_monthly_performance


def load_core_results() -> pd.DataFrame:
    """
    core/run_equity01_eval.py で生成された成果物を読み込む
    
    戻り値:
        paper_trade_with_alpha_beta.parquet のDataFrame
    """
    src = Path("data/processed/paper_trade_with_alpha_beta.parquet")
    if not src.exists():
        raise FileNotFoundError(
            f"{src} がありません。先に core/run_equity01_eval.py を実行してください。"
        )
    
    print(f"読み込み中: {src}")
    df = pd.read_parquet(src)
    df = df.sort_values("trade_date").reset_index(drop=True)
    
    required_cols = ["trade_date", "port_ret_cc", "tpx_ret_cc", "rel_alpha_daily"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise KeyError(
            f"必要な列が見つかりません: {missing_cols}\n"
            f"利用可能な列: {df.columns.tolist()}"
        )
    
    print(f"[OK] データ読み込み完了: {len(df)} 行")
    print(f"  期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    
    return df


def compute_summary_stats(df: pd.DataFrame) -> dict:
    """
    基本統計を計算
    
    戻り値:
        統計情報の辞書
    """
    df = df.copy()
    df = df.sort_values("trade_date")
    
    # 累積リターン
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    # 日次統計
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    # 最大ドローダウン
    cum_port = (1 + df["port_ret_cc"]).cumprod()
    cum_tpx = (1 + df["tpx_ret_cc"]).cumprod()
    
    def max_drawdown(cum_series: pd.Series) -> float:
        running_max = cum_series.expanding().max()
        drawdown = (cum_series - running_max) / running_max
        return drawdown.min()
    
    max_dd_port = max_drawdown(cum_port)
    max_dd_tpx = max_drawdown(cum_tpx)
    
    return {
        "total_port": total_port,
        "total_tpx": total_tpx,
        "total_alpha": total_alpha,
        "mean_alpha_daily": mean_alpha,
        "std_alpha_daily": std_alpha,
        "sharpe_alpha_annual": sharpe_alpha,
        "max_drawdown_port": max_dd_port,
        "max_drawdown_tpx": max_dd_tpx,
        "days": len(df),
        "start_date": df["trade_date"].min(),
        "end_date": df["trade_date"].max(),
    }


def print_summary(stats: dict) -> None:
    """統計サマリを表示"""
    print("\n" + "=" * 60)
    print("=== パフォーマンスサマリ ===")
    print("=" * 60)
    print(f"期間: {stats['start_date']} ～ {stats['end_date']}")
    print(f"日数: {stats['days']}")
    print()
    print("累積リターン:")
    print(f"  ポートフォリオ: {stats['total_port']:+.2%}")
    print(f"  TOPIX:          {stats['total_tpx']:+.2%}")
    print(f"  相対α:          {stats['total_alpha']:+.2%}")
    print()
    print("日次統計:")
    print(f"  平均α（日次）:   {stats['mean_alpha_daily']:+.6f}")
    print(f"  標準偏差:       {stats['std_alpha_daily']:.6f}")
    print(f"  αシャープ（年率）: {stats['sharpe_alpha_annual']:.2f}")
    print()
    print("最大ドローダウン:")
    print(f"  ポートフォリオ: {stats['max_drawdown_port']:+.2%}")
    print(f"  TOPIX:          {stats['max_drawdown_tpx']:+.2%}")
    print("=" * 60)


def save_report(stats: dict, reports_dir: Path) -> None:
    """レポートを保存"""
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # サマリをCSVで保存
    summary_path = reports_dir / "performance_summary.csv"
    summary_df = pd.DataFrame([stats])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] レポート保存: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="equity01 統合評価レポート生成（analysis側）"
    )
    parser.add_argument(
        "--horizon-ensemble",
        action="store_true",
        help="ホライゾンアンサンブル分析を含める（将来実装予定）",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("=== equity01 統合評価レポート生成 ===")
    print("=" * 60)
    
    # core の成果物を読み込み
    try:
        df = load_core_results()
    except FileNotFoundError as e:
        print(f"\n✗ エラー: {e}")
        print("\n先に以下を実行してください:")
        print("  python scripts/core/run_equity01_eval.py")
        sys.exit(1)
    
    # 基本統計を計算
    print("\n=== 基本統計計算 ===")
    stats = compute_summary_stats(df)
    print_summary(stats)
    
    # 月次集計
    print("\n=== 月次集計 ===")
    try:
        compute_monthly_performance()
        print("✓ 月次集計完了")
    except Exception as e:
        print(f"⚠ 月次集計でエラー: {e}")
    
    # レポート保存
    reports_dir = Path("research/reports")
    save_report(stats, reports_dir)
    
    # ホライゾンアンサンブル（将来実装）
    if args.horizon_ensemble:
        print("\n=== ホライゾンアンサンブル分析 ===")
        print("⚠ この機能は将来実装予定です")
        print("  現在は analysis/horizon_ensemble.py を個別に実行してください")
    
    print("\n" + "=" * 60)
    print("=== レポート生成完了 ===")
    print("=" * 60)
    print(f"\nレポート保存先: {reports_dir}")
    print("注意: research/reports/ は .gitignore で除外されています")


if __name__ == "__main__":
    main()
