"""
rolling_relative_alpha.py

moving window 相対α（ウィンドウ長 w 日）を計算するスクリプト。

calc_alpha_beta.py で生成された paper_trade_with_alpha_beta.parquet を読み込み、
複数のウィンドウ（10, 20, 60, 120日）で moving window 相対αを計算します。

定義：
- ポート窓内累積リターン: cum_port_w(t) = Π_{i=t-w+1..t} (1 + port_ret_cc(i))
- TOPIX窓内累積リターン: cum_tpx_w(t) = Π_{i=t-w+1..t} (1 + tpx_ret_cc(i))
- 相対α（窓内）: rel_alpha_w(t) = cum_port_w(t) - cum_tpx_w(t)

出力:
    data/processed/rolling_relative_alpha.parquet
"""
from pathlib import Path

import numpy as np
import pandas as pd

WINDOWS = [10, 20, 60, 120]


def main() -> None:
    # calc_alpha_beta.py が出したファイルを利用
    src = Path("data/processed/paper_trade_with_alpha_beta.parquet")
    if not src.exists():
        raise FileNotFoundError(
            f"{src} がありません。先に calc_alpha_beta.py を実行してください。"
        )

    print(f"読み込み中: {src}")
    df = pd.read_parquet(src)
    df = df.sort_values("trade_date").reset_index(drop=True)

    print(f"データ期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"データ行数: {len(df)}")

    # 基本列
    port = df["port_ret_cc"].astype(float)
    tpx = df["tpx_ret_cc"].astype(float)

    # 出力用 DataFrame（trade_date だけコピー）
    out = df[["trade_date"]].copy()

    print("\n各ウィンドウで moving window 相対αを計算中...")
    for w in WINDOWS:
        print(f"  ウィンドウ {w} 日...", end=" ")

        # 窓内累積リターン（倍率）
        # rolling(w).apply(np.prod, raw=True) で窓内の累積積を計算
        port_cum = (1.0 + port).rolling(w, min_periods=1).apply(np.prod, raw=True)
        tpx_cum = (1.0 + tpx).rolling(w, min_periods=1).apply(np.prod, raw=True)

        out[f"port_cum_{w}d"] = port_cum
        out[f"tpx_cum_{w}d"] = tpx_cum
        out[f"rel_alpha_{w}d"] = port_cum - tpx_cum

        # 有効データ数を確認
        valid_count = out[f"rel_alpha_{w}d"].notna().sum()
        print(f"完了（有効データ: {valid_count} 日）")

    out_path = Path("data/processed/rolling_relative_alpha.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"\n✓ rolling relative alpha saved to: {out_path}")
    print(f"\n出力カラム: {list(out.columns)}")
    print("\n末尾10行:")
    print(out.tail(10))

    # 各ウィンドウの統計情報を表示
    print("\n=== 各ウィンドウの統計情報 ===")
    for w in WINDOWS:
        col = f"rel_alpha_{w}d"
        if col in out.columns:
            alpha_series = out[col].dropna()
            if len(alpha_series) > 0:
                print(f"\n{col}:")
                print(f"  平均: {alpha_series.mean():.6f}")
                print(f"  標準偏差: {alpha_series.std():.6f}")
                print(f"  最小値: {alpha_series.min():.6f}")
                print(f"  最大値: {alpha_series.max():.6f}")
                print(f"  5%分位点: {alpha_series.quantile(0.05):.6f}")
                print(f"  95%分位点: {alpha_series.quantile(0.95):.6f}")
                print(f"  有効データ数: {len(alpha_series)}")


if __name__ == "__main__":
    main()

