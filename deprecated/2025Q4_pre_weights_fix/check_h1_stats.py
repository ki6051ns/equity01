"""
H1バックテストの統計情報を表示するスクリプト
既存の結果ファイルを読み込んで統計情報を表示
"""
import pandas as pd
import numpy as np
from pathlib import Path

# H1の結果を読み込み
h1_path = Path("data/processed/paper_trade_h1.parquet")
if not h1_path.exists():
    print(f"エラー: {h1_path} が見つかりません")
    exit(1)

df_pt = pd.read_parquet(h1_path)
print(f"H1バックテスト結果を読み込み: {len(df_pt)} 日分")

# TOPIXデータを読み込み
tpx_path = Path("data/processed/index_tpx_daily.parquet")
if not tpx_path.exists():
    print(f"エラー: {tpx_path} が見つかりません")
    exit(1)

df_tpx = pd.read_parquet(tpx_path)

# マージ
df_pt["trade_date"] = pd.to_datetime(df_pt["trade_date"])
df_tpx["trade_date"] = pd.to_datetime(df_tpx["trade_date"])
df = df_pt.merge(
    df_tpx[["trade_date", "tpx_ret_cc"]],
    on="trade_date",
    how="inner"
)

# 相対αを計算
df["rel_alpha_daily"] = df["port_ret_cc"] - df["tpx_ret_cc"]
df = df.sort_values("trade_date")

print("\n" + "=" * 60)
print("=== H1 Statistics ===")
print("=" * 60)

# port_ret_cc.describe()
print("\n【port_ret_cc.describe()】")
print(df["port_ret_cc"].describe())

# tpx_ret_cc.describe()
print("\n【tpx_ret_cc.describe()】")
print(df["tpx_ret_cc"].describe())

# 累積パフォーマンス（最終値）
total_port = (1 + df["port_ret_cc"]).prod() - 1
total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
total_alpha = total_port - total_tpx

print("\n【累積パフォーマンス（最終値）】")
print(f"Port: {total_port:+.4%}")
print(f"TOPIX: {total_tpx:+.4%}")
print(f"α: {total_alpha:+.4%}")

# 非ラダー版との相関係数
try:
    paper_trade_path = Path("data/processed/paper_trade_with_alpha_beta.parquet")
    if paper_trade_path.exists():
        df_pt_baseline = pd.read_parquet(paper_trade_path)
        df_pt_baseline = df_pt_baseline.sort_values("trade_date")
        
        # 日付でマージ
        df_merged = df[["trade_date", "port_ret_cc"]].merge(
            df_pt_baseline[["trade_date", "port_ret_cc"]],
            on="trade_date",
            how="inner",
            suffixes=("_ladder", "_baseline")
        )
        
        if len(df_merged) > 0:
            corr = df_merged["port_ret_cc_ladder"].corr(df_merged["port_ret_cc_baseline"])
            print("\n【非ラダー版との相関係数】")
            print(f"correlation: {corr:.4f}")
            print(f"比較日数: {len(df_merged)} 日")
        else:
            print("\n【非ラダー版との相関係数】")
            print("共通日付がありません")
    else:
        print("\n【非ラダー版との相関係数】")
        print(f"paper_trade_with_alpha_beta.parquet が見つかりません")
except Exception as e:
    print(f"\n【非ラダー版との相関係数】")
    print(f"エラー: {e}")

# 年率リターン、年率ボラ、年率Sharpe
days = len(df)
years = days / 252.0

# 年率リターン
annual_return_port = (1 + total_port) ** (1.0 / years) - 1 if years > 0 else 0.0
annual_return_tpx = (1 + total_tpx) ** (1.0 / years) - 1 if years > 0 else 0.0
annual_return_alpha = (1 + total_alpha) ** (1.0 / years) - 1 if years > 0 else 0.0

# 年率ボラ（日次リターンの標準偏差 * sqrt(252)）
annual_vol_port = df["port_ret_cc"].std() * np.sqrt(252)
annual_vol_tpx = df["tpx_ret_cc"].std() * np.sqrt(252)
annual_vol_alpha = df["rel_alpha_daily"].std() * np.sqrt(252)

# 年率Sharpe（リスクフリーレート=0と仮定）
sharpe_port = annual_return_port / annual_vol_port if annual_vol_port > 0 else float("nan")
sharpe_tpx = annual_return_tpx / annual_vol_tpx if annual_vol_tpx > 0 else float("nan")
sharpe_alpha = annual_return_alpha / annual_vol_alpha if annual_vol_alpha > 0 else float("nan")

print("\n【年率統計】")
print(f"期間: {years:.2f} 年 ({days} 日)")
print(f"\nPort:")
print(f"  年率リターン: {annual_return_port:+.4%}")
print(f"  年率ボラ: {annual_vol_port:+.4%}")
print(f"  年率Sharpe: {sharpe_port:+.4f}")
print(f"\nTOPIX:")
print(f"  年率リターン: {annual_return_tpx:+.4%}")
print(f"  年率ボラ: {annual_vol_tpx:+.4%}")
print(f"  年率Sharpe: {sharpe_tpx:+.4f}")
print(f"\nα:")
print(f"  年率リターン: {annual_return_alpha:+.4%}")
print(f"  年率ボラ: {annual_vol_alpha:+.4%}")
print(f"  年率Sharpe: {sharpe_alpha:+.4f}")

print("\n" + "=" * 60)

