#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/eval_stop_regimes.py

STOP条件に基づく戦略評価

cross4の日次リターンとTOPIXリターンを使用して、
STOP条件（alphaのローリング合計<0 かつ TOPIXのローリング合計<0）を定義し、
3つのバリアント（STOP0、Plan A、Plan B）を60日・120日のwindowで評価する。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # 非対話的バックエンド
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_DIR = Path("data/processed")
OUTPUT_DIR = Path("data/processed/stop_regime_plots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# horizon_ensemble.pyからインポート
try:
    from horizon_ensemble import compute_monthly_perf
except ImportError:
    # インポートできない場合は直接定義
    from typing import Tuple
    
    def compute_monthly_perf(df_alpha: pd.DataFrame, label: str, out_prefix: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        月次・年次パフォーマンスを計算
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
        
        # 保存
        monthly_path = Path(f"{out_prefix}_monthly_{label}.parquet")
        monthly_path.parent.mkdir(parents=True, exist_ok=True)
        monthly_returns.to_parquet(monthly_path, index=False)
        
        yearly_path = Path(f"{out_prefix}_yearly_{label}.parquet")
        yearly.to_parquet(yearly_path, index=False)
        
        return monthly_returns, yearly


def load_cross4_returns() -> tuple:
    """
    cross4の日次リターンとTOPIXリターンを読み込む
    
    Returns
    -------
    tuple
        (port_ret, tpx_ret) のタプル（pd.Series）
    """
    cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    
    if not cross4_path.exists():
        raise FileNotFoundError(
            f"{cross4_path} がありません。先に ensemble_variant_cross4.py を実行してください。"
        )
    
    df = pd.read_parquet(cross4_path)
    
    # 日付カラムを統一
    date_col = "trade_date" if "trade_date" in df.columns else "date"
    if date_col not in df.columns:
        raise KeyError(f"日付カラムが見つかりません: {df.columns.tolist()}")
    
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
        # index_tpx_daily.parquetから読み込む
        tpx_path = DATA_DIR / "index_tpx_daily.parquet"
        if tpx_path.exists():
            df_tpx = pd.read_parquet(tpx_path)
            tpx_date_col = "trade_date" if "trade_date" in df_tpx.columns else "date"
            df_tpx[tpx_date_col] = pd.to_datetime(df_tpx[tpx_date_col])
            df_tpx = df_tpx.set_index(tpx_date_col).sort_index()
            if "tpx_ret_cc" in df_tpx.columns:
                tpx_ret = df_tpx["tpx_ret_cc"]
            else:
                raise KeyError(f"TOPIXリターン列が見つかりません: {df_tpx.columns.tolist()}")
        else:
            raise FileNotFoundError(
                f"{cross4_path} にTOPIXリターンがなく、{tpx_path} も見つかりません。"
            )
    else:
        tpx_ret = df[tpx_col]
    
    port_ret = df[port_col]
    
    # インデックスで揃える（inner join）
    common_index = port_ret.index.intersection(tpx_ret.index)
    port_ret = port_ret.loc[common_index]
    tpx_ret = tpx_ret.loc[common_index]
    
    print(f"[INFO] Loaded cross4 returns: {len(port_ret)} days")
    print(f"  Date range: {port_ret.index.min().date()} ～ {port_ret.index.max().date()}")
    
    return port_ret, tpx_ret


def load_inverse_returns() -> pd.Series:
    """
    インバースETF（1569.T）の日次リターンを読み込む
    
    Returns
    -------
    pd.Series
        インバースETFの日次リターン
    """
    # 複数のパスを試す
    inverse_paths = [
        DATA_DIR / "inverse_returns.parquet",
        DATA_DIR / "daily_returns_inverse.parquet",
        Path("data/raw") / "equities" / "1569.T.parquet",
    ]
    
    for path in inverse_paths:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                
                # 日付カラムを確認
                date_col = None
                for col in ["date", "trade_date", "datetime"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col is None:
                    continue
                
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.set_index(date_col).sort_index()
                
                # リターンカラムを確認
                ret_col = None
                for col in ["ret", "inv_ret", "port_return", "return"]:
                    if col in df.columns:
                        ret_col = col
                        break
                
                if ret_col is None:
                    # 価格カラムから計算
                    for col in ["close", "adj_close", "Close", "Adj Close"]:
                        if col in df.columns:
                            ret_col = col
                            df["ret"] = df[col].pct_change()
                            ret_col = "ret"
                            break
                
                if ret_col is None:
                    continue
                
                inv_ret = df[ret_col].dropna()
                print(f"[INFO] Loaded inverse returns from {path}: {len(inv_ret)} days")
                return inv_ret
                
            except Exception as e:
                print(f"[WARN] Failed to load from {path}: {e}")
                continue
    
    # 見つからない場合は警告を出して0リターンで埋める
    print("[WARN] Inverse returns not found. Using zero returns as placeholder.")
    return pd.Series(dtype=float)


def compute_stop_conditions(port_ret: pd.Series, tpx_ret: pd.Series, windows: list = [60, 120]) -> dict:
    """
    STOP条件を計算
    
    ✅ チェック1: ルックアヘッドバイアスを回避
    - 当日リターンを含めたrollingを使わないよう、必ず.shift(1)を使用
    - これにより「前日までの情報で当日の判定」を行う
    
    Parameters
    ----------
    port_ret : pd.Series
        cross4の日次リターン
    tpx_ret : pd.Series
        TOPIXの日次リターン
    windows : list
        ウィンドウサイズのリスト
    
    Returns
    -------
    dict
        {window: stop_condition_series} の辞書
    """
    alpha = port_ret - tpx_ret
    
    stop_conditions = {}
    
    for window in windows:
        # ✅ ルックアヘッドバイアス回避: 前日までの情報を使うため .shift(1)
        roll_alpha = alpha.rolling(window=window, min_periods=1).sum().shift(1)
        roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1)
        
        # 最初の1日目はNaNになるので、False（STOPしない）で埋める
        roll_alpha = roll_alpha.fillna(False)
        roll_tpx = roll_tpx.fillna(False)
        
        # ✅ チェック2: STOPマスクの向き確認
        # stop_cond = True の時は「STOP期間中」（ノーポジ、リターン0）
        stop_cond = (roll_alpha < 0) & (roll_tpx < 0)
        stop_conditions[window] = stop_cond
        
        stop_days = stop_cond.sum()
        stop_pct = stop_days / len(stop_cond) * 100
        print(f"[INFO] STOP condition (window={window}): {stop_days} days ({stop_pct:.1f}%)")
        print(f"  First STOP day: {stop_cond.idxmax() if stop_cond.any() else 'None'}")
    
    return stop_conditions


def compute_strategy_returns(
    port_ret: pd.Series,
    inv_ret: pd.Series,
    stop_conditions: dict,
    windows: list = [60, 120],
) -> dict:
    """
    各戦略のリターンを計算
    
    ✅ チェック2: STOPマスクの向き
    - stop_cond = True の時: STOP期間中（ノーポジ、リターン0）
    - stop_cond = False の時: 通常期間（cross4フル）
    - np.where(condition, value_if_true, value_if_false)
    
    ✅ チェック3: 逆張りしていないか
    - STOP0は完全キャッシュ（リターン0）のみ
    - inverse_retを一切混ぜない
    
    Parameters
    ----------
    port_ret : pd.Series
        cross4の日次リターン
    inv_ret : pd.Series
        インバースETFの日次リターン
    stop_conditions : dict
        STOP条件の辞書
    windows : list
        ウィンドウサイズのリスト
    
    Returns
    -------
    dict
        各戦略のリターンSeriesを含む辞書
    """
    strategies = {}
    
    # Baseline
    strategies["baseline"] = port_ret.copy()
    
    # インバースリターンをport_retのインデックスに合わせる
    if len(inv_ret) > 0:
        common_dates = port_ret.index.intersection(inv_ret.index)
        inv_ret_aligned = inv_ret.reindex(port_ret.index, fill_value=0.0)
    else:
        inv_ret_aligned = pd.Series(0.0, index=port_ret.index)
        print("[WARN] Using zero returns for inverse ETF")
    
    for window in windows:
        stop_cond = stop_conditions[window]
        
        # ✅ STOP0: STOP中はリターン0（キャッシュ100%）
        # np.where(stop_cond, 0.0, port_ret) = stop_condがTrueなら0.0、Falseならport_ret
        ret_stop0 = np.where(stop_cond, 0.0, port_ret.values)
        strategies[f"stop0_{window}"] = pd.Series(ret_stop0, index=port_ret.index)
        
        # ✅ STOP0のチェック: STOP期間中のリターンがほぼ0か確認
        ret_stop0_series = strategies[f"stop0_{window}"]
        stop_ret_mean = ret_stop0_series[stop_cond].mean()
        non_stop_ret_mean = ret_stop0_series[~stop_cond].mean()
        print(f"\n[CHECK] STOP0 {window}d:")
        print(f"  STOP期間中の平均リターン: {stop_ret_mean:.6f} (想定: ~0.0)")
        print(f"  STOP期間外の平均リターン: {non_stop_ret_mean:.6f} (想定: cross4と同等)")
        print(f"  STOP期間中のリターン標準偏差: {ret_stop0_series[stop_cond].std():.6f}")
        
        # ✅ チェック3: STOP0の実効エクスポージャ確認（ウェイトが0または1のみか）
        # STOP期間中は0.0、それ以外は1.0のはず
        # リターンから逆算: ret = weight * port_ret なので、weight = ret / port_ret
        # STOP期間中: ret = 0 なので weight = 0
        # STOP期間外: ret = port_ret なので weight = 1
        # ただしport_retが0に近い日は除く
        mask_nonzero_port = np.abs(port_ret.values) > 1e-6
        weights_implied = np.where(
            mask_nonzero_port,
            ret_stop0 / np.where(port_ret.values != 0, port_ret.values, 1.0),
            np.where(stop_cond, 0.0, 1.0)  # port_ret=0の日はstop_condで判定
        )
        weights_series = pd.Series(weights_implied, index=port_ret.index)
        print(f"  実効ウェイト範囲: [{weights_series.min():.3f}, {weights_series.max():.3f}]")
        print(f"  実効ウェイト平均 (STOP期間中): {weights_series[stop_cond].mean():.6f}")
        print(f"  実効ウェイト平均 (STOP期間外): {weights_series[~stop_cond].mean():.6f}")
        
        # Plan A: STOP中はcross4 75% + inverse 25%（合計100%）
        ret_A = np.where(stop_cond, 0.75 * port_ret.values + 0.25 * inv_ret_aligned.values, port_ret.values)
        strategies[f"planA_{window}"] = pd.Series(ret_A, index=port_ret.index)
        
        # ✅ Plan Aのチェック: STOP期間中のリターンが 0.75*port_ret + 0.25*inv_ret になっているか
        ret_A_series = strategies[f"planA_{window}"]
        stop_ret_mean_A = ret_A_series[stop_cond].mean()
        non_stop_ret_mean_A = ret_A_series[~stop_cond].mean()
        expected_stop_ret_A = (0.75 * port_ret[stop_cond] + 0.25 * inv_ret_aligned[stop_cond]).mean()
        expected_non_stop_ret_A = port_ret[~stop_cond].mean()
        print(f"\n[CHECK] Plan A {window}d:")
        print(f"  STOP期間中の平均リターン: {stop_ret_mean_A:.6f}")
        print(f"    想定値 (0.75*port + 0.25*inv): {expected_stop_ret_A:.6f}")
        print(f"    差分: {abs(stop_ret_mean_A - expected_stop_ret_A):.6f}")
        print(f"  STOP期間外の平均リターン: {non_stop_ret_mean_A:.6f}")
        print(f"    想定値 (portのみ): {expected_non_stop_ret_A:.6f}")
        print(f"    差分: {abs(non_stop_ret_mean_A - expected_non_stop_ret_A):.6f}")
        
        # ✅ Plan Aの実効ウェイト確認
        # STOP期間中: ret = port_ret * w_port + inv_ret * w_inv (w_port=0.75, w_inv=0.25)
        # STOP期間外: ret = port_ret * w_port (w_port=1.0, w_inv=0.0)
        # 実効ウェイトを逆算（簡易版: port_retとinv_retの相関を無視）
        port_ret_vals = port_ret.values
        inv_ret_vals = inv_ret_aligned.values
        
        # STOP期間中: ret_A = 0.75 * port_ret + 0.25 * inv_ret
        # 実際の ret_A と期待値 0.75*port_ret + 0.25*inv_ret を比較
        expected_A_stop = 0.75 * port_ret_vals[stop_cond] + 0.25 * inv_ret_vals[stop_cond]
        actual_A_stop = ret_A[stop_cond]
        diff_A_stop = np.abs(actual_A_stop - expected_A_stop).mean()
        print(f"  STOP期間中の実効エクスポージャ合計 (推定): {0.75 + 0.25:.2f} (想定: 1.0)")
        print(f"  STOP期間中のリターン誤差平均: {diff_A_stop:.6f} (想定: ~0.0)")
        
        expected_A_non_stop = port_ret_vals[~stop_cond]
        actual_A_non_stop = ret_A[~stop_cond]
        diff_A_non_stop = np.abs(actual_A_non_stop - expected_A_non_stop).mean()
        print(f"  STOP期間外の実効エクスポージャ合計 (推定): {1.0 + 0.0:.2f} (想定: 1.0)")
        print(f"  STOP期間外のリターン誤差平均: {diff_A_non_stop:.6f} (想定: ~0.0)")
        
        # ✅ Plan AのインバースETF相関チェック
        if len(inv_ret) > 0 and inv_ret_aligned.notna().sum() > 10:
            # STOP期間中のPlanAリターンとinverseリターンの相関
            corr_A_stop = ret_A_series[stop_cond].corr(inv_ret_aligned[stop_cond])
            # STOP期間外のPlanAリターンとinverseリターンの相関（通常は低いはず）
            corr_A_non_stop = ret_A_series[~stop_cond].corr(inv_ret_aligned[~stop_cond])
            print(f"  STOP期間中のPlanA vs inverse相関: {corr_A_stop:.4f} (想定: 正の相関)")
            print(f"  STOP期間外のPlanA vs inverse相関: {corr_A_non_stop:.4f} (想定: 低い相関)")
        
        # Plan B: STOP中はcross4 50% + cash 50%
        ret_B = np.where(stop_cond, 0.5 * port_ret.values, port_ret.values)
        strategies[f"planB_{window}"] = pd.Series(ret_B, index=port_ret.index)
    
    return strategies


def eval_strategy(ret_series: pd.Series, tpx_ret: pd.Series, name: str) -> dict:
    """
    戦略のパフォーマンス指標を計算して表示
    
    Parameters
    ----------
    ret_series : pd.Series
        戦略の日次リターン
    tpx_ret : pd.Series
        TOPIXの日次リターン
    name : str
        戦略名
    
    Returns
    -------
    dict
        パフォーマンス指標を含む辞書
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
    月次・年次パフォーマンスを表示
    """
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("%", ""),
        out_prefix=str(DATA_DIR / "stop_regime")
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


def compute_simple_stop_benchmark(port_ret: pd.Series, tpx_ret: pd.Series, window: int = 60) -> pd.Series:
    """
    ベンチマーク用の簡易STOPルール
    「TOPIXが過去N日トータルでマイナスなら100%キャッシュ、それ以外はcross4」
    
    Parameters
    ----------
    port_ret : pd.Series
        cross4の日次リターン
    tpx_ret : pd.Series
        TOPIXの日次リターン
    window : int
        ウィンドウサイズ
    
    Returns
    -------
    pd.Series
        ベンチマーク戦略の日次リターン
    """
    # ✅ ルックアヘッドバイアス回避
    roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1).fillna(False)
    stop_cond = roll_tpx < 0
    
    # STOP中はリターン0、それ以外はcross4
    ret_benchmark = np.where(stop_cond, 0.0, port_ret.values)
    
    return pd.Series(ret_benchmark, index=port_ret.index)


def plot_stop_timeline(
    port_ret: pd.Series,
    tpx_ret: pd.Series,
    stop_conditions: dict,
    output_dir: Path,
) -> None:
    """
    時系列で「いつSTOPしているか」をプロット
    
    Parameters
    ----------
    port_ret : pd.Series
        cross4の日次リターン
    tpx_ret : pd.Series
        TOPIXの日次リターン
    stop_conditions : dict
        STOP条件の辞書
    output_dir : Path
        出力ディレクトリ
    """
    for window in stop_conditions.keys():
        stop_cond = stop_conditions[window]
        
        # 累積リターンを計算
        cum_port = (1 + port_ret).cumprod()
        cum_tpx = (1 + tpx_ret).cumprod()
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True, height_ratios=[3, 1])
        
        dates = port_ret.index
        
        # 上段: 累積リターン曲線
        cum_port_pct = (cum_port - 1) * 100
        cum_tpx_pct = (cum_tpx - 1) * 100
        ax1.plot(dates, cum_port_pct, label="cross4", linewidth=2, alpha=0.8, color="#2E86AB")
        ax1.plot(dates, cum_tpx_pct, label="TOPIX", linewidth=2, alpha=0.8, color="#FF6B6B")
        
        # STOP期間を背景色で表示（シンプルな方法）
        y_min, y_max = ax1.get_ylim()
        stop_flag_values = stop_cond.astype(int).values
        ax1.fill_between(dates, y_min, y_max, 
                         where=stop_flag_values > 0, alpha=0.2, color='red', 
                         label='STOP期間', interpolate=True)
        
        ax1.set_ylabel("Cumulative Return (%)", fontsize=12)
        ax1.set_title(f"STOP Condition Timeline (window={window}d)", fontsize=14, fontweight="bold")
        ax1.legend(fontsize=11, loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
        
        # 下段: STOPフラグ（1/0）
        stop_flag = stop_cond.astype(int)
        ax2.fill_between(dates, 0, stop_flag, alpha=0.5, color='red', label='STOP Flag')
        ax2.set_ylabel("STOP Flag", fontsize=12)
        ax2.set_ylim(-0.1, 1.1)
        ax2.set_yticks([0, 1])
        ax2.set_yticklabels(['OFF', 'ON'])
        ax2.legend(fontsize=11, loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        # 日付フォーマット
        ax2.xaxis.set_major_locator(mdates.YearLocator())
        ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
        
        plt.tight_layout()
        
        fig_path = output_dir / f"stop_timeline_{window}d.png"
        fig.savefig(fig_path, dpi=150, bbox_inches='tight')
        print(f"[INFO] Saved STOP timeline to {fig_path}")
        plt.close(fig)


def plot_strategy_comparison(results: dict) -> plt.Figure:
    """
    戦略の累積リターン曲線とドローダウン曲線を描画
    
    Parameters
    ----------
    results : dict
        eval_strategy()の結果を格納した辞書
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    
    # 比較する戦略（60日のみ）
    strategy_keys = ["baseline", "stop0_60", "planA_60", "planB_60"]
    strategy_names = {
        "baseline": "Baseline (cross4)",
        "stop0_60": "STOP0 60d",
        "planA_60": "Plan A 60d (cross4 75% + inverse 25%)",
        "planB_60": "Plan B 60d (cash 50%)",
    }
    colors = {
        "baseline": "#2E86AB",
        "stop0_60": "#FF6B6B",
        "planA_60": "#6BCF7F",
        "planB_60": "#FFD93D",
    }
    
    # 累積リターン曲線
    for key in strategy_keys:
        if key in results:
            result = results[key]
            cum_curve = result["cumulative_curve"]
            dates = cum_curve.index
            
            ax1.plot(dates, (cum_curve - 1) * 100, 
                    label=strategy_names.get(key, key),
                    linewidth=2, alpha=0.8, color=colors.get(key, "#000000"))
    
    ax1.set_ylabel("Cumulative Return (%)", fontsize=12)
    ax1.set_title("Cumulative Return Comparison", fontsize=14, fontweight="bold")
    ax1.legend(fontsize=11, loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    
    # ドローダウン曲線
    for key in strategy_keys:
        if key in results:
            result = results[key]
            dd = result["drawdown"]
            dates = dd.index
            
            ax2.plot(dates, dd * 100,
                    label=strategy_names.get(key, key),
                    linewidth=2, alpha=0.8, color=colors.get(key, "#000000"))
    
    ax2.set_ylabel("Drawdown (%)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=12)
    ax2.set_title("Drawdown Comparison", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11, loc='lower left')
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.5, alpha=0.5)
    
    # 日付フォーマット
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator((1, 7)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    
    plt.tight_layout()
    return fig


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== STOP条件に基づく戦略評価 ===")
    print("=" * 80)
    
    # 1. データ読み込み
    print("\n[STEP 1] Loading data...")
    port_ret, tpx_ret = load_cross4_returns()
    inv_ret = load_inverse_returns()
    
    # インバースリターンをport_retのインデックスに合わせる
    if len(inv_ret) > 0:
        common_dates = port_ret.index.intersection(inv_ret.index)
        if len(common_dates) == 0:
            print("[WARN] No overlapping dates between port_ret and inv_ret. Using zero returns.")
            inv_ret = pd.Series(0.0, index=port_ret.index)
        else:
            inv_ret = inv_ret.reindex(port_ret.index, fill_value=0.0)
            print(f"[INFO] Aligned inverse returns: {inv_ret.notna().sum()} days")
    else:
        inv_ret = pd.Series(0.0, index=port_ret.index)
    
    # 2. STOP条件を計算
    print("\n[STEP 2] Computing STOP conditions...")
    windows = [60, 120]
    stop_conditions = compute_stop_conditions(port_ret, tpx_ret, windows=windows)
    
    # 3. 各戦略のリターンを計算
    print("\n[STEP 3] Computing strategy returns...")
    print("=" * 80)
    strategies = compute_strategy_returns(port_ret, inv_ret, stop_conditions, windows=windows)
    
    # ✅ チェック4: ベンチマークテスト
    print("\n[CHECK 4] Simple STOP benchmark test...")
    print("=" * 80)
    for window in windows:
        ret_benchmark = compute_simple_stop_benchmark(port_ret, tpx_ret, window=window)
        benchmark_result = eval_strategy(ret_benchmark, tpx_ret, f"Benchmark (TOPIX<0, {window}d)")
        
        # サマリー表示
        cum_bench = benchmark_result["cumulative"]
        ann_bench = benchmark_result["annualized"]
        sharpe_bench = benchmark_result["alpha_sharpe"]
        dd_bench = benchmark_result["max_dd"]
        print(f"Benchmark {window}d: Cum={cum_bench*100:+.2f}%, Ann={ann_bench*100:+.2f}%, "
              f"Sharpe={sharpe_bench:.2f}, MaxDD={dd_bench*100:+.2f}%")
        
        strategies[f"benchmark_{window}"] = ret_benchmark
    
    # 4. パフォーマンス評価
    print("\n[STEP 4] Evaluating strategies...")
    print("=" * 80)
    
    results = {}
    
    # Baseline
    results["baseline"] = eval_strategy(strategies["baseline"], tpx_ret, "Baseline cross4")
    
    # STOP0
    results["stop0_60"] = eval_strategy(strategies["stop0_60"], tpx_ret, "STOP0 60d")
    results["stop0_120"] = eval_strategy(strategies["stop0_120"], tpx_ret, "STOP0 120d")
    
    # Plan A
    results["planA_60"] = eval_strategy(strategies["planA_60"], tpx_ret, "Plan A 60d (cross4 75% + inverse 25%)")
    results["planA_120"] = eval_strategy(strategies["planA_120"], tpx_ret, "Plan A 120d (cross4 75% + inverse 25%)")
    
    # Plan B
    results["planB_60"] = eval_strategy(strategies["planB_60"], tpx_ret, "Plan B 60d (cash 50%)")
    results["planB_120"] = eval_strategy(strategies["planB_120"], tpx_ret, "Plan B 120d (cash 50%)")
    
    # 5. 年次・月次パフォーマンス計算
    print("\n[STEP 5] Computing monthly and yearly performance...")
    print("=" * 80)
    
    for key, result in results.items():
        if "df_alpha" in result:
            print(f"\n{result['name']}")
            print("-" * 80)
            print_monthly_yearly_performance(result["df_alpha"], result["name"])
    
    # 6. 可視化
    print("\n[STEP 6] Creating visualizations...")
    fig = plot_strategy_comparison(results)
    fig_path = OUTPUT_DIR / "strategy_comparison_60d.png"
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"[INFO] Saved strategy comparison to {fig_path}")
    plt.close(fig)
    
    # ✅ チェック5: STOPタイムラインの可視化
    print("\n[CHECK 5] Creating STOP timeline plots...")
    plot_stop_timeline(port_ret, tpx_ret, stop_conditions, OUTPUT_DIR)
    
    # 7. サマリーテーブル
    print("\n" + "=" * 80)
    print("=== パフォーマンスサマリー ===")
    print("=" * 80)
    
    summary_data = []
    for key, result in results.items():
        summary_data.append({
            "Strategy": result["name"],
            "Cumulative (%)": f"{result['cumulative']*100:+.2f}",
            "Annualized (%)": f"{result['annualized']*100:+.2f}",
            "Alpha Sharpe": f"{result['alpha_sharpe']:.2f}",
            "MaxDD (%)": f"{result['max_dd']*100:+.2f}",
        })
    
    summary_df = pd.DataFrame(summary_data)
    print("\n" + summary_df.to_string(index=False))
    
    # 結果を保存
    print("\n[STEP 7] Saving results...")
    output_path = DATA_DIR / "stop_regime_strategies.parquet"
    
    # すべての戦略リターンをDataFrameにまとめる
    output_df = pd.DataFrame(strategies)
    output_df.index.name = "date"
    output_df = output_df.reset_index()
    output_df.to_parquet(output_path, index=False)
    print(f"[INFO] Saved strategy returns to {output_path}")
    
    print("\n" + "=" * 80)
    print("=== 完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()

