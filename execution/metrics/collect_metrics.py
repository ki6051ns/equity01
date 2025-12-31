"""
collect_metrics.py

execution/execution_outputs/ の order_intent_*.csv を走査して、日次に集計する。
"""
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd


def collect_metrics_from_outputs(output_dir: Path = Path("execution/execution_outputs")) -> pd.DataFrame:
    """
    order_intent_*.csv を走査してメトリクスを集計する。
    
    Parameters
    ----------
    output_dir : Path
        execution_outputsディレクトリのパス
    
    Returns
    -------
    pd.DataFrame
        日次メトリクス（run_date, latest_date, n_symbols, daily_turnover,
                       gross_notional, gross_buy_notional, gross_sell_notional,
                       req_margin_simple）
    """
    if not output_dir.exists():
        print(f"警告: {output_dir} が存在しません")
        return pd.DataFrame()
    
    # order_intent_*.csv を検索（SKIPファイルは除外）
    intent_files = sorted(output_dir.glob("order_intent_*.csv"))
    intent_files = [f for f in intent_files if "_SKIP" not in f.name]
    
    if not intent_files:
        print(f"警告: order_intent_*.csv が見つかりません")
        return pd.DataFrame()
    
    metrics_list = []
    
    for file_path in intent_files:
        try:
            # ファイル名から日付を抽出（order_intent_YYYYMMDD.csv）
            date_str = file_path.stem.replace("order_intent_", "")
            if len(date_str) == 8 and date_str.isdigit():
                run_date = datetime.strptime(date_str, "%Y%m%d").date()
            else:
                # ファイル名から取得できない場合はファイルの更新日時を使用
                run_date = datetime.fromtimestamp(file_path.stat().st_mtime).date()
            
            # CSVを読み込む
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            
            if df.empty:
                continue
            
            # latest_dateを取得（存在する場合）
            if "latest_date" in df.columns:
                latest_date = df["latest_date"].iloc[0] if not df["latest_date"].isna().all() else None
            else:
                latest_date = None
            
            # メトリクスを計算
            n_symbols = len(df)
            
            # daily_turnover = sum(abs(delta_weight))
            if "delta_weight" in df.columns:
                daily_turnover = df["delta_weight"].abs().sum()
            else:
                daily_turnover = 0.0
            
            # gross_notional = sum(abs(notional_delta))
            if "notional_delta" in df.columns:
                gross_notional = df["notional_delta"].abs().sum()
            else:
                gross_notional = 0.0
            
            # gross_buy_notional, gross_sell_notional
            if "notional_delta" in df.columns:
                buy_df = df[df["notional_delta"] > 0]
                sell_df = df[df["notional_delta"] < 0]
                gross_buy_notional = buy_df["notional_delta"].abs().sum() if not buy_df.empty else 0.0
                gross_sell_notional = sell_df["notional_delta"].abs().sum() if not sell_df.empty else 0.0
            else:
                gross_buy_notional = 0.0
                gross_sell_notional = 0.0
            
            # req_margin_simple = gross_buy_notional / leverage_ratio
            if "leverage_ratio" in df.columns and not df["leverage_ratio"].isna().all():
                leverage_ratio = df["leverage_ratio"].iloc[0]
                if leverage_ratio > 0:
                    req_margin_simple = gross_buy_notional / leverage_ratio
                else:
                    req_margin_simple = 0.0
            else:
                # leverage_ratioが無い場合は1.0と仮定
                req_margin_simple = gross_buy_notional / 1.0 if gross_buy_notional > 0 else 0.0
            
            metrics = {
                "run_date": run_date.strftime("%Y-%m-%d"),
                "latest_date": latest_date if latest_date else "",
                "n_symbols": n_symbols,
                "daily_turnover": daily_turnover,
                "gross_notional": gross_notional,
                "gross_buy_notional": gross_buy_notional,
                "gross_sell_notional": gross_sell_notional,
                "req_margin_simple": req_margin_simple,
            }
            
            metrics_list.append(metrics)
            
        except Exception as e:
            print(f"警告: {file_path.name} の処理中にエラーが発生しました: {e}")
            continue
    
    if not metrics_list:
        return pd.DataFrame()
    
    df_metrics = pd.DataFrame(metrics_list)
    
    # run_dateでソート
    if "run_date" in df_metrics.columns:
        df_metrics = df_metrics.sort_values("run_date").reset_index(drop=True)
    
    return df_metrics


def save_metrics(df_metrics: pd.DataFrame, output_path: Path = Path("execution/execution_outputs/metrics_daily.csv")) -> None:
    """
    メトリクスをCSVに保存する。
    
    Parameters
    ----------
    df_metrics : pd.DataFrame
        メトリクスDataFrame
    output_path : Path
        出力パス
    """
    if df_metrics.empty:
        print("警告: メトリクスが空です。ファイルを保存しません。")
        return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"メトリクスを保存しました: {output_path}")
    print(f"集計件数: {len(df_metrics)} 日")


def main():
    """メトリクス集計のメイン処理"""
    print("=" * 80)
    print("execution metrics集計")
    print("=" * 80)
    
    # メトリクスを集計
    print("\n[1] order_intent_*.csv を走査中...")
    df_metrics = collect_metrics_from_outputs()
    
    if df_metrics.empty:
        print("メトリクスが集計できませんでした。")
        return
    
    print(f"集計完了: {len(df_metrics)} 日のデータ")
    
    # メトリクスを表示
    print("\n[2] 集計結果:")
    print(df_metrics.to_string(index=False))
    
    # メトリクスを保存
    print("\n[3] メトリクスを保存中...")
    save_metrics(df_metrics)
    
    print("\n" + "=" * 80)
    print("メトリクス集計完了")
    print("=" * 80)


if __name__ == "__main__":
    main()

