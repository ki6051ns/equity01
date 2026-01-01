#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/backtest_from_weights.py

weightsからreturnsを計算するバックテスト（analysis内で完結、coreへ書き戻し禁止）

入力:
- cross4_target_weights.parquet（date, symbol, weight）
- 価格データ（またはリターン）

出力:
- data/processed/weights_bt/cross4_from_weights.parquet（trade_date, port_ret_cc, cumulativeなど）

重要: この段階ではまだprdに接続しない。まずanalysis内で一致検証。
"""

import sys
import io
import os
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32':
    # 環境変数を設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 標準出力のエンコーディングをUTF-8に設定
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.7以前の互換性
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # 既に設定されている場合はスキップ
        pass

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/backtest_from_weights.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from scripts.tools.lib import data_loader

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
WEIGHTS_BT_DIR = DATA_DIR / "weights_bt"
WEIGHTS_BT_DIR.mkdir(parents=True, exist_ok=True)


def load_weights(weights_path: Path) -> pd.DataFrame:
    """
    weightsファイルを読み込む
    
    Parameters
    ----------
    weights_path : Path
        weightsファイルのパス
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    if not weights_path.exists():
        raise FileNotFoundError(f"weightsファイルが見つかりません: {weights_path}")
    
    df = pd.read_parquet(weights_path)
    
    # 必須カラムを確認
    required_cols = ["date", "symbol", "weight"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"必須カラムが不足しています: {missing_cols}")
    
    # dateをdatetimeに変換
    df["date"] = pd.to_datetime(df["date"])
    
    return df


def calculate_returns_from_weights(
    df_weights: pd.DataFrame,
    prices_df: pd.DataFrame = None
) -> pd.DataFrame:
    """
    weightsからreturnsを計算する
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame
    prices_df : pd.DataFrame, optional
        価格データ（指定しない場合はdata_loaderから読み込む）
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc, cumulative を含むDataFrame
    """
    # 価格データを読み込む
    if prices_df is None:
        prices_df = data_loader.load_prices()
    
    # 価格データの日付をdatetimeに変換
    if "date" in prices_df.columns:
        prices_df["date"] = pd.to_datetime(prices_df["date"])
    
    # リターンを計算
    if "symbol" in prices_df.columns:
        prices_df = prices_df.sort_values(["symbol", "date"])
        # adj_closeが存在する場合はそれを使用、なければcloseを使用
        if "adj_close" in prices_df.columns:
            prices_df["ret_1d"] = prices_df.groupby("symbol")["adj_close"].pct_change()
        else:
            prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
    else:
        if "adj_close" in prices_df.columns:
            prices_df["ret_1d"] = prices_df["adj_close"].pct_change()
        else:
            prices_df["ret_1d"] = prices_df["close"].pct_change()
    
    # 【修正】trade_dateの正本をpricesの営業日カレンダーにする
    # weightsはasof mergeで前日ウェイトを持ち越す
    trade_dates = sorted(prices_df["date"].unique())
    
    # weightsを日付でソート（asof merge用）
    df_weights = df_weights.sort_values(["date", "symbol"])
    df_weights = df_weights.set_index("date")
    
    rows = []
    cumulative = 1.0
    
    for i, trade_date in enumerate(trade_dates):
        # 最初の日は前日がないのでスキップ
        if i == 0:
            continue
        
        # 前日のweightsを取得（w[t-1]）
        prev_date = trade_dates[i - 1]
        
        # asof merge: 前日以前の最新のweightsを使用
        weights_prev = df_weights[df_weights.index <= prev_date]
        if weights_prev.empty:
            continue
        
        # 前日の日付で最新のweightsを取得
        weights_day = weights_prev[weights_prev.index == weights_prev.index.max()].copy()
        if weights_day.empty:
            continue
        
        # 前日のweightsをSeriesに変換（symbolをindexに）
        weights_series = weights_day.reset_index().set_index("symbol")["weight"]
        
        # 当日の価格データを取得（r[t]）
        if "symbol" in prices_df.columns:
            prices_day = prices_df[prices_df["date"] == trade_date].copy()
            if prices_day.empty:
                continue
            
            # symbolをindexに
            prices_day = prices_day.set_index("symbol")
        else:
            prices_day = prices_df[prices_df["date"] == trade_date].copy()
            if prices_day.empty:
                continue
            prices_day = prices_day.set_index(prices_day.index)
        
        # 共通のsymbolを取得
        common_symbols = weights_series.index.intersection(prices_day.index)
        if len(common_symbols) == 0:
            continue
        
        # 共通symbolのweightsとreturnsを取得
        weights_aligned = weights_series[common_symbols]
        rets_aligned = prices_day.loc[common_symbols, "ret_1d"]
        
        # NaNを0に置換
        weights_aligned = weights_aligned.fillna(0.0)
        rets_aligned = rets_aligned.fillna(0.0)
        
        # ポートフォリオリターンを計算: port_ret[t] = sum_i w_i[t-1] * r_i[t]
        port_ret_cc = float((weights_aligned * rets_aligned).sum())
        
        # 累積を更新
        cumulative *= (1.0 + port_ret_cc)
        
        rows.append({
            "trade_date": trade_date,
            "port_ret_cc": port_ret_cc,
            "cumulative": cumulative,
        })
    
    df_result = pd.DataFrame(rows)
    
    if df_result.empty:
        return pd.DataFrame(columns=["trade_date", "port_ret_cc", "cumulative"])
    
    # TOPIXデータを読み込んで相対αを計算
    tpx_path = DATA_DIR / "index_tpx_daily.parquet"
    if tpx_path.exists():
        df_tpx = pd.read_parquet(tpx_path)
        if "trade_date" in df_tpx.columns:
            df_tpx["trade_date"] = pd.to_datetime(df_tpx["trade_date"])
            
            # 【整合性チェック】trade_dateが営業日カレンダーに整合しているか確認
            tpx_dates = set(df_tpx["trade_date"].unique())
            result_dates = set(df_result["trade_date"].unique())
            if not result_dates <= tpx_dates:
                missing_in_tpx = result_dates - tpx_dates
                print(f"[WARN] trade_date整合性: {len(missing_in_tpx)} days in result but not in TPX calendar")
                print(f"[WARN] 例: {sorted(list(missing_in_tpx))[:5]}")
            
            df_result = df_result.merge(
                df_tpx[["trade_date", "tpx_ret_cc"]],
                on="trade_date",
                how="left"
            )
            # bfill()は削除（ルックアヘッドバイアス回避）
            # ffill()のみで前日値を持ち越す（未来データ注入なし）
            df_result["tpx_ret_cc"] = df_result["tpx_ret_cc"].ffill()
            
            # 欠損が残る場合は警告ログを出して除外
            missing = df_result["tpx_ret_cc"].isna().sum()
            if missing > 0:
                print(f"[WARN] TPX_MISSING n={missing} days; drop for alpha calc")
            
            df_result["rel_alpha_daily"] = df_result["port_ret_cc"] - df_result["tpx_ret_cc"]
            # α統計は欠損を除外したdfで計算
            df_result = df_result.dropna(subset=["tpx_ret_cc"])
        else:
            df_result["tpx_ret_cc"] = 0.0
            df_result["rel_alpha_daily"] = df_result["port_ret_cc"]
    else:
        df_result["tpx_ret_cc"] = 0.0
        df_result["rel_alpha_daily"] = df_result["port_ret_cc"]
    
    return df_result.sort_values("trade_date").reset_index(drop=True)


def compute_monthly_perf(df_alpha: pd.DataFrame, label: str, out_prefix: str):
    """
    月次・年次パフォーマンスを計算（eval_stop_regimes.py準拠）
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date").reset_index(drop=True)
    
    if not {"port_ret_cc", "tpx_ret_cc"}.issubset(df.columns):
        raise KeyError(
            f"必要な列 'port_ret_cc', 'tpx_ret_cc' が見つかりません: {df.columns.tolist()}"
        )
    
    # 年・月を抽出
    df["year"] = df["trade_date"].dt.year
    df["month"] = df["trade_date"].dt.month
    
    # 空のDataFrameの場合は空の結果を返す
    if len(df) == 0:
        monthly_returns = pd.DataFrame(columns=["year", "month", "port_return", "tpx_return", "days", "rel_alpha"])
        yearly = pd.DataFrame(columns=["year", "port_return", "tpx_return", "rel_alpha", "days"])
        return monthly_returns, yearly
    
    # 月次累積リターン（倍率ベース）
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
    )
    
    monthly_returns = monthly_returns.reset_index()
    
    # 相対αの月次版（倍率ベースの差）
    monthly_returns["rel_alpha"] = (
        monthly_returns["port_return"] - monthly_returns["tpx_return"]
    )
    
    # 年次集計
    yearly = (
        monthly_returns.groupby("year")
        .agg(
            {
                "port_return": lambda x: (1.0 + x).prod() - 1.0,
                "tpx_return": lambda x: (1.0 + x).prod() - 1.0,
                "rel_alpha": "sum",
                "days": "sum",
            }
        )
        .reset_index()
    )
    yearly["rel_alpha"] = yearly["port_return"] - yearly["tpx_return"]
    
    # 保存（eval_stop_regimes.py準拠）
    monthly_path = Path(f"{out_prefix}_monthly_{label}.parquet")
    monthly_path.parent.mkdir(parents=True, exist_ok=True)
    monthly_returns.to_parquet(monthly_path, index=False)
    
    yearly_path = Path(f"{out_prefix}_yearly_{label}.parquet")
    yearly.to_parquet(yearly_path, index=False)
    
    return monthly_returns, yearly


def eval_strategy(ret_series: pd.Series, tpx_ret: pd.Series, name: str) -> dict:
    """
    戦略のパフォーマンス指標を計算して表示（eval_stop_regimes.py準拠）
    """
    # インデックスを揃える
    common_index = ret_series.index.intersection(tpx_ret.index)
    port_ret_aligned = ret_series.loc[common_index]
    tpx_ret_aligned = tpx_ret.loc[common_index]
    
    df = pd.DataFrame({
        "trade_date": common_index,
        "port_ret_cc": port_ret_aligned.values,
        "tpx_ret_cc": tpx_ret_aligned.values,
    })
    df["alpha"] = df["port_ret_cc"] - df["tpx_ret_cc"]
    df["rel_alpha_daily"] = df["alpha"]  # 互換性のため
    
    # 累積リターン
    cum_port = (1 + df["port_ret_cc"]).prod() - 1
    
    # 年率リターン
    days = len(df)
    years = days / 252.0
    ann_port = (1 + cum_port) ** (1.0 / years) - 1 if years > 0 else 0.0
    
    # 年率αとシャープ
    ann_alpha = df["alpha"].mean() * 252
    alpha_std = df["alpha"].std() * np.sqrt(252)
    sharpe_a = ann_alpha / alpha_std if alpha_std > 0 else np.nan
    
    # 最大ドローダウン
    cum_curve = (1 + df["port_ret_cc"]).cumprod()
    dd = cum_curve / cum_curve.cummax() - 1
    max_dd = dd.min()
    
    # 表示
    print(f"=== {name} ===")
    print(f"  Cumulative: {cum_port*100:6.2f}%")
    print(f"  Annualized: {ann_port*100:6.2f}%")
    print(f"  Alpha Sharpe: {sharpe_a:5.2f}")
    print(f"  MaxDD: {max_dd*100:6.2f}%")
    print()
    
    return {
        "name": name,
        "cumulative": cum_port,
        "annualized": ann_port,
        "alpha_sharpe": sharpe_a,
        "max_dd": max_dd,
        "returns": port_ret_aligned,
        "cumulative_curve": cum_curve,
        "drawdown": dd,
        "df_alpha": df,  # 年次・月次計算用
    }


def print_monthly_yearly_performance(df_alpha: pd.DataFrame, name: str):
    """
    月次・年次パフォーマンスを表示（eval_stop_regimes.py準拠）
    """
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("%", ""),
        out_prefix=str(WEIGHTS_BT_DIR)
    )
    
    # 月次リターン表
    print(f"\n【{name} - 月次リターン（相対α）】")
    try:
        pivot_monthly = monthly.pivot_table(
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
        print(monthly[["year", "month", "port_return", "tpx_return", "rel_alpha"]].to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次リターン表
    print(f"\n【{name} - 年次リターン】")
    yearly_display = yearly[["year", "port_return", "tpx_return", "rel_alpha"]].copy()
    print(yearly_display.to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次統計
    print(f"\n【{name} - 年次統計】")
    yearly_port_mean = yearly["port_return"].mean()
    yearly_tpx_mean = yearly["tpx_return"].mean()
    yearly_alpha_mean = yearly["rel_alpha"].mean()
    yearly_alpha_std = yearly["rel_alpha"].std()
    yearly_alpha_sharpe = yearly_alpha_mean / yearly_alpha_std if yearly_alpha_std > 0 else np.nan
    yearly_win_rate = (yearly["rel_alpha"] > 0).mean()
    
    print(f"年率平均（Port）: {yearly_port_mean:+.4%}")
    print(f"年率平均（TOPIX）: {yearly_tpx_mean:+.4%}")
    print(f"年率平均（α）: {yearly_alpha_mean:+.4%}")
    print(f"年率標準偏差（α）: {yearly_alpha_std:+.4%}")
    print(f"年率αシャープ: {yearly_alpha_sharpe:+.4f}")
    print(f"年間勝率: {yearly_win_rate:+.2%}")


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="weightsからreturnsを計算するバックテスト"
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=str(WEIGHTS_DIR / "cross4_target_weights.parquet"),
        help="weightsファイルのパス"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(WEIGHTS_BT_DIR / "cross4_from_weights.parquet"),
        help="出力ファイルのパス"
    )
    
    args = parser.parse_args()
    
    weights_path = Path(args.weights)
    output_path = Path(args.output)
    
    print("=" * 80)
    print("=== WeightsからReturns計算（weights版cross4） ===")
    print("=" * 80)
    print(f"\n入力: {weights_path}")
    print(f"出力: {output_path}")
    
    # weightsを読み込む
    print("\n[STEP 1] weightsを読み込み中...")
    df_weights = load_weights(weights_path)
    print(f"  ✓ {len(df_weights)} rows")
    print(f"  日付範囲: {df_weights['date'].min()} ～ {df_weights['date'].max()}")
    
    # returnsを計算
    print("\n[STEP 2] returnsを計算中...")
    df_result = calculate_returns_from_weights(df_weights)
    
    if df_result.empty:
        print("\n[ERROR] returnsの計算に失敗しました。")
        return
    
    print(f"  ✓ {len(df_result)} 日分のリターンを計算")
    
    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_parquet(output_path, index=False)
    print(f"\n✓ 結果を保存: {output_path}")
    
    # eval_stop_regimes.pyと同じ形式で集計・表示
    print("\n" + "=" * 80)
    print("【パフォーマンス統計】")
    print("=" * 80)
    
    # TOPIXリターンをSeriesに変換
    tpx_ret = df_result.set_index("trade_date")["tpx_ret_cc"]
    port_ret = df_result.set_index("trade_date")["port_ret_cc"]
    
    # 戦略名
    strategy_name = "STOPなし (cross4)"
    
    # パフォーマンス評価
    result = eval_strategy(port_ret, tpx_ret, strategy_name)
    
    # 月次・年次パフォーマンス表示
    print_monthly_yearly_performance(result["df_alpha"], strategy_name)
    
    print("\n" + "=" * 80)
    print("完了: weights→returns計算完了")
    print("=" * 80)


if __name__ == "__main__":
    main()

