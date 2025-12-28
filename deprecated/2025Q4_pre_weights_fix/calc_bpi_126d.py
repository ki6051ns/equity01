#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/calc_bpi_126d.py

半年（126営業日）ローリング最大ドローダウンから
BPI（ = 半年内の最大DDのうち、今どれだけ沈んでいるか）を計算するスクリプト。

対象:
- rank_only
- variant_cross3（B50% : E50%）
- TOPIX（ベンチマーク比較用）
"""

import pandas as pd
import numpy as np
from pathlib import Path

# 半年 ≒ 126 営業日
WINDOW_DAYS = 126

DATA_DIR = Path("data/processed")


def ensure_equity_col(
    df: pd.DataFrame,
    date_col: str = "date",
    equity_col: str = "equity",
    ret_col: str = "port_ret",
) -> pd.DataFrame:
    """
    BPI計算用に「equity」（価格・指数レベル）列を用意する。

    優先順:
      1) equity_col が既にあればそれを使う
      2) 累積リターン列（cum_port_ens, cumulative_port, cum_port）があればそれを使う
      3) 日次リターン列 ret_col から累積
      4) 'port' が「累積リターン（倍率 or %）」なら 1 + port を equity とみなす

    必要に応じてこの関数だけ調整すればOK。
    """
    df = df.copy()
    df = df.sort_values(date_col)

    if equity_col in df.columns:
        return df

    # 累積リターン列を探す（複数の候補をチェック）
    cum_cols = ["cum_port_ens", "cumulative_port", "cum_port", "equity", "cum_tpx"]
    for cum_col in cum_cols:
        if cum_col in df.columns:
            df[equity_col] = df[cum_col].astype(float)
            return df

    # 日次リターン列を探す（複数の候補をチェック）
    ret_cols = [
        ret_col,
        "port_ret_cc",
        "port_ret_cc_ens",
        "port_ret",
        "ret",
        "tpx_ret_cc",
    ]
    for rcol in ret_cols:
        if rcol in df.columns:
            # 日次リターンがある場合（例: 0.01 = +1%）
            df[equity_col] = (1.0 + df[rcol].astype(float)).cumprod()
            return df

    # port が「累積リターン（+233% → 2.33）」 or 「トータルリターン倍率（2.33）」想定
    if "port" in df.columns:
        # ここでは「1 + port」を指数レベルとみなす（必要ならここはプロジェクト仕様に合わせて修正）
        df[equity_col] = 1.0 + df["port"].astype(float)
        return df

    raise ValueError(
        f"equity / 累積リターン / port_ret のいずれも見つからないため、BPIを計算できません。"
        f"利用可能な列: {list(df.columns)}"
    )


def compute_bpi_from_equity(
    df: pd.DataFrame,
    date_col: str = "date",
    equity_col: str = "equity",
    window: int = WINDOW_DAYS,
) -> pd.DataFrame:
    """
    指数レベル（equity）から半年ローリング最大DDベースの BPI を計算。

    BPI_t = max( 0, (rolling_peak - equity_t) / rolling_peak )

    Parameters
    ----------
    df : pd.DataFrame
        入力データ（date_col と equity_col を含む）
    date_col : str
        日付列名
    equity_col : str
        指数レベル列名
    window : int
        ローリングウィンドウ（営業日数）

    Returns
    -------
    pd.DataFrame
        date, bpi, rolling_peak, drawdown を含むDataFrame
    """
    df = df.copy().sort_values(date_col)
    eq = df[equity_col].astype(float)

    # ローリングピーク（過去window日間の最大値）
    rolling_peak = eq.rolling(window, min_periods=1).max()
    
    # ドローダウン = (ピーク - 現在値) / ピーク
    drawdown = (rolling_peak - eq) / rolling_peak
    
    # BPI = ドローダウンを0でフロア
    bpi = drawdown.clip(lower=0.0)

    out = df[[date_col]].copy()
    out["bpi"] = bpi
    out["rolling_peak"] = rolling_peak
    out["drawdown"] = drawdown

    return out


def main():
    """
    メイン処理: rank_only、variant_cross3、TOPIX のBPIを計算
    """
    base_dir = DATA_DIR

    configs = [
        dict(
            name="rank_only",
            path=base_dir / "horizon_ensemble_rank_only.parquet",
            equity_source="cum_port_ens",
            ret_col="port_ret_cc",
        ),
        dict(
            name="cross3",
            path=base_dir / "horizon_ensemble_variant_cross3.parquet",
            equity_source="cum_port_ens",
            ret_col="port_ret_cc",
        ),
        dict(
            name="topix",
            path=base_dir / "horizon_ensemble_rank_only.parquet",  # TOPIXデータは同じファイル内にある
            equity_source="cum_tpx",
            ret_col="tpx_ret_cc",
        ),
    ]

    merged_list = []

    for cfg in configs:
        name = cfg["name"]
        path = cfg["path"]
        equity_source = cfg.get("equity_source")
        ret_col = cfg.get("ret_col", "port_ret_cc")

        if not path.exists():
            print(f"[WARN] {name}: file not found: {path}")
            continue

        print(f"[INFO] loading {name} from {path}")
        df = pd.read_parquet(path)

        # date カラム名を標準化（必要ならここでリネーム）
        if "date" not in df.columns:
            # よくある代替案を一応ケア
            for cand in ["trade_date", "datetime", "ts"]:
                if cand in df.columns:
                    df = df.rename(columns={cand: "date"})
                    print(f"  [INFO] 列名を変換: {cand} -> date")
                    break

        if "date" not in df.columns:
            print(f"[ERROR] {name}: date列が見つかりません。利用可能な列: {list(df.columns)}")
            continue

        # date列をdatetime型に変換
        df["date"] = pd.to_datetime(df["date"])

        # TOPIXの場合、専用のequity列を準備
        if name == "topix":
            if equity_source and equity_source in df.columns:
                df["equity"] = df[equity_source].astype(float)
            else:
                # cum_tpxが無い場合は、tpx_ret_ccから累積計算
                if ret_col in df.columns:
                    df["equity"] = (1.0 + df[ret_col].astype(float)).cumprod()
                else:
                    print(f"[ERROR] {name}: {equity_source} または {ret_col} が見つかりません。")
                    continue
        else:
            # ポートフォリオの場合は既存のロジックを使用
            try:
                df = ensure_equity_col(df, date_col="date", equity_col="equity", ret_col=ret_col)
            except ValueError as e:
                print(f"[ERROR] {name}: {e}")
                continue

        # BPI計算
        bpi_df = compute_bpi_from_equity(
            df,
            date_col="date",
            equity_col="equity",
            window=WINDOW_DAYS,
        )

        # 列名に戦略名のサフィックスを付与
        bpi_df = bpi_df.rename(
            columns={
                "bpi": f"bpi_{name}",
                "rolling_peak": f"rolling_peak_{name}",
                "drawdown": f"drawdown_{name}",
            }
        )

        out_path = base_dir / f"bpi_{name}_126d.parquet"
        bpi_df.to_parquet(out_path, index=False)
        print(f"[INFO] saved {name} BPI -> {out_path}")
        print(f"  [INFO] データ期間: {bpi_df['date'].min()} ～ {bpi_df['date'].max()}")
        print(f"  [INFO] データ行数: {len(bpi_df)}")
        print(f"  [INFO] BPI統計: min={bpi_df[f'bpi_{name}'].min():.4f}, max={bpi_df[f'bpi_{name}'].max():.4f}, mean={bpi_df[f'bpi_{name}'].mean():.4f}")

        merged_list.append(bpi_df.set_index("date"))

    # rank_only / cross3 / topix を横持ちでマージした版も吐き出す
    if merged_list:
        merged = pd.concat(merged_list, axis=1).reset_index()
        out_path = base_dir / "bpi_rank_only_vs_cross3_vs_topix_126d.parquet"
        merged.to_parquet(out_path, index=False)
        print(f"\n[INFO] saved merged BPI -> {out_path}")
        print(f"  [INFO] データ期間: {merged['date'].min()} ～ {merged['date'].max()}")
        print(f"  [INFO] データ行数: {len(merged)}")
        
        # 相関を表示
        if "bpi_rank_only" in merged.columns and "bpi_cross3" in merged.columns:
            corr = merged["bpi_rank_only"].corr(merged["bpi_cross3"])
            print(f"  [INFO] BPI相関 (rank_only vs cross3): {corr:.4f}")
        if "bpi_rank_only" in merged.columns and "bpi_topix" in merged.columns:
            corr = merged["bpi_rank_only"].corr(merged["bpi_topix"])
            print(f"  [INFO] BPI相関 (rank_only vs topix): {corr:.4f}")
        if "bpi_cross3" in merged.columns and "bpi_topix" in merged.columns:
            corr = merged["bpi_cross3"].corr(merged["bpi_topix"])
            print(f"  [INFO] BPI相関 (cross3 vs topix): {corr:.4f}")

    print("\n" + "=" * 80)
    print("=== BPI計算完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()
