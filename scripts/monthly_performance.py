"""
monthly_performance.py

日次パフォーマンスデータから月次・年次の集計を行うスクリプト。

paper_trade_with_alpha_beta.parquet を読み込み、
年別・月別のパフォーマンスを自動集計します。

出力:
    data/processed/monthly_returns.parquet
    data/processed/monthly_relative_alpha.parquet
"""
from pathlib import Path

import pandas as pd


def compute_monthly_performance() -> None:
    """
    paper_trade_with_alpha_beta.parquet から月次・年次のパフォーマンスを計算
    """
    src = Path("data/processed/paper_trade_with_alpha_beta.parquet")
    if not src.exists():
        raise FileNotFoundError(
            f"{src} がありません。先に calc_alpha_beta.py を実行してください。"
        )

    print(f"読み込み中: {src}")
    df = pd.read_parquet(src)
    df = df.sort_values("trade_date").reset_index(drop=True)

    if not {"port_ret_cc", "tpx_ret_cc"}.issubset(df.columns):
        raise KeyError(
            f"必要な列 'port_ret_cc', 'tpx_ret_cc' が見つかりません: {df.columns.tolist()}"
        )

    # 年・月を抽出
    df["year"] = df["trade_date"].dt.year
    df["month"] = df["trade_date"].dt.month

    print(f"データ期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"データ行数: {len(df)}")

    # 月次累積リターン（倍率ベース）
    print("\n月次リターンを計算中...")
    monthly_returns = (
        df.groupby(["year", "month"])
        .apply(
            lambda x: pd.Series(
                {
                    "port_return": (1.0 + x["port_ret_cc"]).prod() - 1.0,
                    "tpx_return": (1.0 + x["tpx_ret_cc"]).prod() - 1.0,
                    "days": len(x),
                }
            )
        )
        .reset_index()
    )

    # 相対αの月次版（倍率ベースの差）
    monthly_returns["rel_alpha"] = (
        monthly_returns["port_return"] - monthly_returns["tpx_return"]
    )

    # 保存
    out_path = Path("data/processed/monthly_returns.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    monthly_returns.to_parquet(out_path, index=False)

    print(f"\n✓ monthly returns saved to: {out_path}")

    # 月次相対αのみを別ファイルに保存（後で使いやすいように）
    monthly_alpha = monthly_returns[["year", "month", "rel_alpha", "days"]].copy()
    alpha_path = Path("data/processed/monthly_relative_alpha.parquet")
    monthly_alpha.to_parquet(alpha_path, index=False)

    print(f"✓ monthly relative alpha saved to: {alpha_path}")

    # 年次集計
    print("\n年次集計を計算中...")
    yearly = (
        monthly_returns.groupby("year")
        .agg(
            {
                "port_return": lambda x: (1.0 + x).prod() - 1.0,
                "tpx_return": lambda x: (1.0 + x).prod() - 1.0,
                "rel_alpha": "sum",  # 月次相対αの累積（簡易版）
                "days": "sum",
            }
        )
        .reset_index()
    )
    yearly["rel_alpha"] = yearly["port_return"] - yearly["tpx_return"]  # 正確な年次相対α

    # 表示用のテーブル作成（月次パンチカード表）
    print("\n=== 月次パフォーマンス表 ===")
    pivot_port = monthly_returns.pivot_table(
        index="year", columns="month", values="port_return", aggfunc="first"
    )
    pivot_tpx = monthly_returns.pivot_table(
        index="year", columns="month", values="tpx_return", aggfunc="first"
    )
    pivot_alpha = monthly_returns.pivot_table(
        index="year", columns="month", values="rel_alpha", aggfunc="first"
    )

    # 月名を設定
    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    pivot_port.columns = [month_names[i - 1] if i in pivot_port.columns else "" for i in range(1, 13)]
    pivot_tpx.columns = [month_names[i - 1] if i in pivot_tpx.columns else "" for i in range(1, 13)]
    pivot_alpha.columns = [month_names[i - 1] if i in pivot_alpha.columns else "" for i in range(1, 13)]

    # 年次合計を追加
    pivot_port["年間"] = yearly.set_index("year")["port_return"]
    pivot_tpx["年間"] = yearly.set_index("year")["tpx_return"]
    pivot_alpha["年間"] = yearly.set_index("year")["rel_alpha"]

    print("\n【ポートフォリオ月次リターン】")
    print(pivot_port.to_string(float_format="{:+.2%}".format))

    print("\n【TOPIX月次リターン】")
    print(pivot_tpx.to_string(float_format="{:+.2%}".format))

    print("\n【相対α月次リターン】")
    print(pivot_alpha.to_string(float_format="{:+.2%}".format))

    print("\n【年次サマリ】")
    print(yearly.to_string(index=False, float_format="{:+.2%}".format))

    # 統計情報
    print("\n=== 統計情報 ===")
    print(f"月次ポートフォリオ平均リターン: {monthly_returns['port_return'].mean():+.4%}")
    print(f"月次TOPIX平均リターン: {monthly_returns['tpx_return'].mean():+.4%}")
    print(f"月次相対α平均: {monthly_returns['rel_alpha'].mean():+.4%}")
    print(f"月次相対α標準偏差: {monthly_returns['rel_alpha'].std():+.4%}")
    if monthly_returns['rel_alpha'].std() > 0:
        sharpe = monthly_returns['rel_alpha'].mean() / monthly_returns['rel_alpha'].std() * (12 ** 0.5)
        print(f"月次相対αシャープ（年率換算）: {sharpe:+.4f}")
    else:
        print("月次相対αシャープ（年率換算）: N/A")


if __name__ == "__main__":
    compute_monthly_performance()
