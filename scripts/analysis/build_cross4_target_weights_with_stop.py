#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/build_cross4_target_weights_with_stop.py

STOP付cross4 target weightsを生成する（analysis内で完結、coreへ書き戻し禁止）

入力:
- data/processed/weights/cross4_target_weights.parquet（STOP無しのcross4 weights）
- または data/processed/horizon_ensemble_variant_cross4.parquet（STOP条件計算用）

出力（研究用）:
- data/processed/weights/cross4_target_weights_stop0_w60.parquet（STOP0, window=60）
- data/processed/weights/cross4_target_weights_stop0_w120.parquet（STOP0, window=120）
- data/processed/weights/cross4_target_weights_planA_w60.parquet（Plan A, window=60）
- data/processed/weights/cross4_target_weights_planA_w120.parquet（Plan A, window=120）
- data/processed/weights/cross4_target_weights_planB_w60.parquet（Plan B, window=60）
- data/processed/weights/cross4_target_weights_planB_w120.parquet（Plan B, window=120）

STOPロジック（eval_stop_regimes.py準拠）:
- STOP条件: (alphaのローリング合計 < 0) & (TOPIXのローリング合計 < 0)
- STOP0: STOP期間中はweights=0（完全キャッシュ）
- Plan A: STOP期間中はweightsを維持（実際のリターン調整は別途）
- Plan B: STOP期間中はweightsを0.5倍

重要: この段階ではまだprdに接続しない。まずanalysis内で一致検証。
"""

import sys
from pathlib import Path
from typing import Dict

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/build_cross4_target_weights_with_stop.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

# 共通定数からインバースETF ticker定数をインポート
try:
    from scripts.constants import INVERSE_ETF_TICKER
except ImportError:
    # フォールバック: 直接定義
    INVERSE_ETF_TICKER = "1569.T"  # インバースTOPIX連動ETF

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
RESEARCH_REPORTS_DIR = DATA_DIR / "research" / "reports"
RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_cross4_weights() -> pd.DataFrame:
    """
    STOP無しのcross4 target weightsを読み込む
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    """
    path = WEIGHTS_DIR / "cross4_target_weights.parquet"
    
    if not path.exists():
        raise FileNotFoundError(
            f"cross4 target weightsファイルが見つかりません: {path}\n"
            "先に build_cross4_target_weights.py を実行してください。"
        )
    
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    
    return df


def load_cross4_returns_for_stop(force_rebuild: bool = False) -> pd.DataFrame:
    """
    STOP条件計算用のcross4 returnsを読み込む
    
    Parameters
    ----------
    force_rebuild : bool
        互換性のための引数（現在は未使用。既存のreturnsファイルを読み込む）
    
    Returns
    -------
    pd.DataFrame
        trade_date, port_ret_cc, tpx_ret_cc を含むDataFrame
    """
    # 既存のreturnsファイルを使用（weights_bt/cross4_from_weights.parquet）
    weights_bt_path = DATA_DIR / "weights_bt" / "cross4_from_weights.parquet"
    if weights_bt_path.exists():
        try:
            df = pd.read_parquet(weights_bt_path)
            if "trade_date" in df.columns and "port_ret_cc" in df.columns:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                
                # 既に tpx_ret_cc が入っている場合は、二重マージしない
                if "tpx_ret_cc" in df.columns:
                    df["tpx_ret_cc"] = df["tpx_ret_cc"].fillna(0.0)
                    return df[["trade_date", "port_ret_cc", "tpx_ret_cc"]]
                
                # suffix 付きが既にある場合（過去の処理や別経路で入ったケース）
                if "tpx_ret_cc_x" in df.columns or "tpx_ret_cc_y" in df.columns:
                    col = "tpx_ret_cc_y" if "tpx_ret_cc_y" in df.columns else "tpx_ret_cc_x"
                    df["tpx_ret_cc"] = df[col].fillna(0.0)
                    return df[["trade_date", "port_ret_cc", "tpx_ret_cc"]]
                
                # TOPIXリターンを追加
                tpx_path = DATA_DIR / "index_tpx_daily.parquet"
                if tpx_path.exists():
                    df_tpx = pd.read_parquet(tpx_path)
                    if "trade_date" in df_tpx.columns and "tpx_ret_cc" in df_tpx.columns:
                        df_tpx["trade_date"] = pd.to_datetime(df_tpx["trade_date"])
                        
                        # 既に tpx_ret_cc がある場合は削除してからマージ
                        if "tpx_ret_cc" in df.columns:
                            df = df.drop(columns=["tpx_ret_cc"])
                        
                        # merge（suffixesを指定してtpx側を明確に識別）
                        df = df.merge(
                            df_tpx[["trade_date", "tpx_ret_cc"]].rename(columns={"tpx_ret_cc": "tpx_ret_cc_tpx"}),
                            on="trade_date",
                            how="left"
                        )
                        
                        # tpx_ret_cc_tpx を tpx_ret_cc にリネーム
                        if "tpx_ret_cc_tpx" in df.columns:
                            df["tpx_ret_cc"] = df["tpx_ret_cc_tpx"]
                            df = df.drop(columns=["tpx_ret_cc_tpx"])
                        else:
                            raise KeyError(
                                f"tpx_ret_cc_tpx not found after merge. cols={df.columns.tolist()}"
                            )
                        
                        df["tpx_ret_cc"] = df["tpx_ret_cc"].fillna(0.0)
                        return df[["trade_date", "port_ret_cc", "tpx_ret_cc"]]
                    else:
                        print(f"[WARN] {tpx_path} に必要なカラムがありません。")
                        tpx_has_trade_date = "trade_date" in df_tpx.columns
                        tpx_has_tpx_ret_cc = "tpx_ret_cc" in df_tpx.columns
                        print(f"  'trade_date' in columns: {tpx_has_trade_date}")
                        print(f"  'tpx_ret_cc' in columns: {tpx_has_tpx_ret_cc}")
                        print(f"  利用可能なカラム: {df_tpx.columns.tolist()}")
                else:
                    print(f"[WARN] TOPIXリターンファイルが見つかりません: {tpx_path}")
        except Exception as e:
            print(f"[WARN] weights版cross4 returnsの読み込みに失敗: {e}")
            # フォールバックに進む
    
    # フォールバック: 既存のreturn合成cross4
    return_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
    if return_path.exists():
        df = pd.read_parquet(return_path)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            
            # ポートフォリオリターンカラムを確認
            port_col = None
            for col in ["port_ret_cc", "port_ret_cc_ens", "combined_ret"]:
                if col in df.columns:
                    port_col = col
                    break
            
            if port_col is None:
                raise KeyError(f"ポートフォリオリターン列が見つかりません: {df.columns.tolist()}")
            
            # TOPIXリターンを追加
            tpx_path = DATA_DIR / "index_tpx_daily.parquet"
            if tpx_path.exists():
                df_tpx = pd.read_parquet(tpx_path)
                if "trade_date" in df_tpx.columns:
                    df_tpx["trade_date"] = pd.to_datetime(df_tpx["trade_date"])
                    if "tpx_ret_cc" in df_tpx.columns:
                        # 既に tpx_ret_cc がある場合は削除してからマージ
                        if "tpx_ret_cc" in df.columns:
                            df = df.drop(columns=["tpx_ret_cc"])
                        
                        # merge（suffixesを指定してtpx側を明確に識別）
                        df = df.merge(
                            df_tpx[["trade_date", "tpx_ret_cc"]].rename(columns={"tpx_ret_cc": "tpx_ret_cc_tpx"}),
                            on="trade_date",
                            how="left"
                        )
                        
                        # tpx_ret_cc_tpx を tpx_ret_cc にリネーム
                        if "tpx_ret_cc_tpx" in df.columns:
                            df["tpx_ret_cc"] = df["tpx_ret_cc_tpx"]
                            df = df.drop(columns=["tpx_ret_cc_tpx"])
                        
                        df["tpx_ret_cc"] = df["tpx_ret_cc"].fillna(0.0)
                        # ポートフォリオリターンカラムを統一
                        df = df.rename(columns={port_col: "port_ret_cc"})
                        return df[["trade_date", "port_ret_cc", "tpx_ret_cc"]]
            else:
                raise FileNotFoundError(
                    f"TOPIXリターンファイルが見つかりません: {tpx_path}"
                )
    
    raise FileNotFoundError(
        f"cross4 returnsファイルが見つかりません。\n"
        f"以下のいずれかが必要です:\n"
        f"  - {weights_bt_path}\n"
        f"  - {return_path}\n"
        f"また、TOPIXリターンファイル ({DATA_DIR / 'index_tpx_daily.parquet'}) も必要です。"
    )


def compute_stop_conditions(port_ret: pd.Series, tpx_ret: pd.Series, windows: list = [60, 120]) -> Dict[int, pd.Series]:
    """
    STOP条件を計算（eval_stop_regimes.py準拠）
    
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
    Dict[int, pd.Series]
        {window: stop_condition_series} の辞書
    """
    alpha = port_ret - tpx_ret
    
    stop_conditions = {}
    
    for window in windows:
        # ルックアヘッドバイアス回避: 前日までの情報を使うため .shift(1)
        roll_alpha = alpha.rolling(window=window, min_periods=1).sum().shift(1)
        roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1)
        
        # 最初の1日目はNaNになるので、0.0（STOPしない）で埋める（型安全性のためFalseではなく0.0）
        roll_alpha = roll_alpha.fillna(0.0)
        roll_tpx = roll_tpx.fillna(0.0)
        
        # stop_cond = True の時は「STOP期間中」（ノーポジ、リターン0）
        # roll_alpha, roll_tpxは0.0で埋められているので、比較は安全
        stop_cond = (roll_alpha < 0) & (roll_tpx < 0)
        stop_conditions[window] = stop_cond
        
        stop_days = stop_cond.sum()
        stop_pct = stop_days / len(stop_cond) * 100
        print(f"[INFO] STOP condition (window={window}): {stop_days} days ({stop_pct:.1f}%)")
    
    return stop_conditions


def apply_stop_to_weights(
    df_weights: pd.DataFrame,
    stop_conditions: Dict[int, pd.Series],
    strategy: str,
    window: int,
    inverse_symbol: str = None
) -> pd.DataFrame:
    """
    STOP条件をweightsに適用（eval_stop_regimes.py準拠）
    
    Parameters
    ----------
    df_weights : pd.DataFrame
        date, symbol, weight を含むDataFrame
    stop_conditions : Dict[int, pd.Series]
        STOP条件の辞書
    strategy : str
        "stop0", "planA", "planB" のいずれか
    window : int
        ウィンドウサイズ
    inverse_symbol : str
        インバースETFシンボル（デフォルト: "1569.T"）
    
    Returns
    -------
    pd.DataFrame
        STOP適用後のweights（date, symbol, weight）
        
    Notes
    -----
    eval_stop_regimes.py準拠の定義:
    - STOP0: STOP期間中は全銘柄weight=0（sum=0、100% cash）
    - PlanA: STOP期間中は全銘柄weightを0.75倍、1569.Tを0.25で追加（sum=1）
    - PlanB: STOP期間中は全銘柄weightを0.5倍（sum=0.5、残り50%はcash、正規化しない）
    """
    # インバースETF tickerが指定されていない場合は定数を使用
    if inverse_symbol is None:
        inverse_symbol = INVERSE_ETF_TICKER
    
    df = df_weights.copy()
    
    if window not in stop_conditions:
        raise ValueError(f"STOP condition for window={window} not found")
    
    stop_cond = stop_conditions[window]
    
    # STOP条件を日付ごとにマージ
    stop_df = pd.DataFrame({
        "date": stop_cond.index,
        "stop": stop_cond.values
    })
    stop_df["date"] = pd.to_datetime(stop_df["date"])
    
    df = df.merge(stop_df, on="date", how="left")
    df["stop"] = df["stop"].fillna(False)
    
    # 戦略に応じてweightsを調整
    if strategy == "stop0":
        # STOP0: STOP期間中は全銘柄weight=0（sum=0、100% cash）
        df["weight"] = df.apply(
            lambda row: 0.0 if row["stop"] else row["weight"],
            axis=1
        )
        # 正規化しない（sum=0のまま）
        
    elif strategy == "planA":
        # Plan A: STOP日のみ cross4 75% + inverse 25%、非STOP日は cross4 100%（inv=0）
        # 禁止ティッカー（1356.Tなど）は常に0.0
        banned_symbols = {"1356.T"}  # PlanAでは1569.T以外のインバース系を禁止
        
        # 禁止ティッカーは常に0.0に設定
        df.loc[df["symbol"].isin(banned_symbols), "weight"] = 0.0
        
        # 日付ごとに処理
        result_rows = []
        for date in df["date"].unique():
            day_df = df[df["date"] == date].copy()
            is_stop_day = day_df["stop"].iloc[0] if len(day_df) > 0 and "stop" in day_df.columns else False
            
            # 非インバース銘柄のマスク
            non_inv_mask = day_df["symbol"] != inverse_symbol
            # 禁止ティッカーも除外
            non_inv_mask = non_inv_mask & (~day_df["symbol"].isin(banned_symbols))
            
            # 非インバース銘柄のweight合計
            sum_non_inv = day_df.loc[non_inv_mask, "weight"].sum()
            
            if is_stop_day:
                # STOP日: 非invを0.75にスケール、invを0.25に設定
                if sum_non_inv > 0:
                    # 非インバース銘柄を0.75倍にスケール
                    day_df.loc[non_inv_mask, "weight"] *= (0.75 / sum_non_inv)
                else:
                    # 非invが空の場合（異常ケース）は全て0に
                    day_df.loc[non_inv_mask, "weight"] = 0.0
                
                # インバースETFを0.25に設定（既存があれば更新、なければ追加）
                inv_mask = day_df["symbol"] == inverse_symbol
                if inv_mask.any():
                    day_df.loc[inv_mask, "weight"] = 0.25
                else:
                    # 新規追加
                    new_inv_row = pd.DataFrame({
                        "date": [date],
                        "symbol": [inverse_symbol],
                        "weight": [0.25],
                        "stop": [True]
                    })
                    day_df = pd.concat([day_df, new_inv_row], ignore_index=True)
            else:
                # 非STOP日: inv=0.0、非invを1.0に正規化
                # インバースETFを0.0に設定
                inv_mask = day_df["symbol"] == inverse_symbol
                if inv_mask.any():
                    day_df.loc[inv_mask, "weight"] = 0.0
                
                # 非インバース銘柄を1.0に正規化
                if sum_non_inv > 0:
                    day_df.loc[non_inv_mask, "weight"] *= (1.0 / sum_non_inv)
                else:
                    # 非invが空の場合（異常ケース）は全て0に
                    day_df.loc[non_inv_mask, "weight"] = 0.0
            
            # 合計が1.0であることを確認（assert）
            total_weight = day_df["weight"].sum()
            if abs(total_weight - 1.0) > 1e-6:
                raise ValueError(
                    f"PlanA weights合計が1.0ではありません: date={date}, total={total_weight}, "
                    f"is_stop={is_stop_day}"
                )
            
            result_rows.append(day_df)
        
        df = pd.concat(result_rows, ignore_index=True)
        
    elif strategy == "planB":
        # PlanB: STOP期間中は全銘柄weightを0.5倍（sum=0.5、残り50%はcash）
        df["weight"] = df.apply(
            lambda row: row["weight"] * 0.5 if row["stop"] else row["weight"],
            axis=1
        )
        # 正規化しない（sum=0.5のまま、残り50%はcash扱い）
        
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    # stop列を削除
    df = df.drop(columns=["stop"])
    
    return df


def main():
    """メイン関数"""
    print("=" * 80)
    print("=== STOP付cross4 Target Weights 生成 ===")
    print("=" * 80)
    
    # cross4 weightsを読み込む
    print("\n[STEP 1] cross4 target weightsを読み込み中...")
    try:
        df_weights = load_cross4_weights()
        print(f"  ✓ {len(df_weights)} rows")
        print(f"  期間: {df_weights['date'].min()} ～ {df_weights['date'].max()}")
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # cross4 returnsを読み込む（STOP条件計算用）
    print("\n[STEP 2] cross4 returnsを読み込み中（STOP条件計算用）...")
    try:
        df_returns = load_cross4_returns_for_stop()
        print(f"  ✓ {len(df_returns)} 日分")
        
        # リターンをSeriesに変換
        df_returns = df_returns.sort_values("trade_date").reset_index(drop=True)
        port_ret = df_returns.set_index("trade_date")["port_ret_cc"]
        tpx_ret = df_returns.set_index("trade_date")["tpx_ret_cc"]
    except FileNotFoundError as e:
        print(f"  ✗ エラー: {e}")
        return 1
    
    # STOP条件を計算
    print("\n[STEP 3] STOP条件を計算中...")
    stop_conditions = compute_stop_conditions(port_ret, tpx_ret, windows=[60, 120])
    
    # 各戦略・各windowでweightsを生成
    print("\n[STEP 4] STOP付weightsを生成中...")
    strategies = ["stop0", "planA", "planB"]
    windows = [60, 120]
    
    for strategy in strategies:
        for window in windows:
            print(f"\n  [{strategy.upper()}] window={window}")
            
            df_stop_weights = apply_stop_to_weights(df_weights, stop_conditions, strategy, window, inverse_symbol=INVERSE_ETF_TICKER)
            
            # 保存
            output_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
            df_stop_weights.to_parquet(output_path, index=False)
            print(f"    ✓ 保存: {output_path}")
            print(f"      rows: {len(df_stop_weights)}")
            print(f"      最終日のweight合計: {df_stop_weights[df_stop_weights['date'] == df_stop_weights['date'].max()]['weight'].sum():.6f}")
    
    print("\n" + "=" * 80)
    print("完了: STOP付cross4 Target Weights生成完了")
    print("=" * 80)
    
    # STOP日のweights検証（サニティチェック）
    print("\n" + "=" * 80)
    print("【STOP日weights検証】")
    print("=" * 80)
    for strategy in strategies:
        for window in windows:
            verify_stop_weights(strategy, window)
    
    return 0


def verify_stop_weights(strategy: str, window: int):
    """
    STOP日のweightsを検証してCSVに出力
    
    Parameters
    ----------
    strategy : str
        "stop0", "planA", "planB" のいずれか
    window : int
        ウィンドウサイズ（60, 120）
    """
    weights_path = WEIGHTS_DIR / f"cross4_target_weights_{strategy}_w{window}.parquet"
    if not weights_path.exists():
        print(f"[WARN] {weights_path} が見つかりません。スキップします。")
        return
    
    df_weights = pd.read_parquet(weights_path)
    df_weights["date"] = pd.to_datetime(df_weights["date"])
    
    # STOP条件を再計算（検証用）
    try:
        df_returns = load_cross4_returns_for_stop()
        df_returns = df_returns.sort_values("trade_date").reset_index(drop=True)
        port_ret = df_returns.set_index("trade_date")["port_ret_cc"]
        tpx_ret = df_returns.set_index("trade_date")["tpx_ret_cc"]
        stop_conditions = compute_stop_conditions(port_ret, tpx_ret, windows=[window])
        stop_cond = stop_conditions[window]
    except Exception as e:
        print(f"[WARN] STOP条件の計算に失敗: {e}")
        return
    
    # STOP条件を日付ごとにマージ
    stop_df = pd.DataFrame({
        "date": stop_cond.index,
        "stop_flag": stop_cond.values.astype(int)
    })
    stop_df["date"] = pd.to_datetime(stop_df["date"])
    
    # STOP日だけを抽出
    stop_dates = stop_df[stop_df["stop_flag"] == 1]["date"].unique()
    
    if len(stop_dates) == 0:
        print(f"[INFO] {strategy} w{window}: STOP日が見つかりません")
        return
    
    # 各STOP日のweightsを検証
    results = []
    for date in stop_dates:
        day_weights = df_weights[df_weights["date"] == date].copy()
        if day_weights.empty:
            continue
        
        inv_mask = day_weights["symbol"] == INVERSE_ETF_TICKER
        inv_weight = day_weights.loc[inv_mask, "weight"].sum()
        non_inv_weight_sum = day_weights.loc[~inv_mask, "weight"].sum()
        total_sum = day_weights["weight"].sum()
        
        results.append({
            "date": date,
            "strategy": strategy,
            "window": window,
            "inverse_weight": inv_weight,
            "non_inverse_weight_sum": non_inv_weight_sum,
            "total_weight_sum": total_sum,
            "inverse_symbol": INVERSE_ETF_TICKER,
            "has_inverse": inv_weight > 0.0,
        })
    
    if not results:
        print(f"[INFO] {strategy} w{window}: 検証可能なSTOP日がありません")
        return
    
    df_check = pd.DataFrame(results)
    
    # 検証結果を表示
    print(f"\n[{strategy.upper()} w{window}] STOP日検証結果:")
    print(f"  STOP日数: {len(df_check)}")
    print(f"  インバースETF ticker: {INVERSE_ETF_TICKER}")
    print(f"  平均インバースweight: {df_check['inverse_weight'].mean():.6f}")
    print(f"  平均非インバースweight合計: {df_check['non_inverse_weight_sum'].mean():.6f}")
    print(f"  平均合計weight: {df_check['total_weight_sum'].mean():.6f}")
    
    # PlanAの場合の特別チェック
    if strategy == "planA":
        expected_inv = 0.25
        expected_non_inv = 0.75
        expected_total = 1.0
        print(f"  [PlanA期待値] inv={expected_inv}, non_inv={expected_non_inv}, total={expected_total}")
        inv_diff = abs(df_check['inverse_weight'].mean() - expected_inv)
        non_inv_diff = abs(df_check['non_inverse_weight_sum'].mean() - expected_non_inv)
        total_diff = abs(df_check['total_weight_sum'].mean() - expected_total)
        if inv_diff > 0.01 or non_inv_diff > 0.01 or total_diff > 0.01:
            print(f"  ⚠ 期待値との差分が大きい: inv_diff={inv_diff:.6f}, non_inv_diff={non_inv_diff:.6f}, total_diff={total_diff:.6f}")
        else:
            print(f"  ✓ 期待値と一致（許容誤差内）")
    
    # PlanBの場合の特別チェック
    elif strategy == "planB":
        expected_total = 0.5  # cash 50%
        print(f"  [PlanB期待値] total={expected_total} (cash 50%)")
        total_diff = abs(df_check['total_weight_sum'].mean() - expected_total)
        if total_diff > 0.01:
            print(f"  ⚠ 期待値との差分が大きい: total_diff={total_diff:.6f}")
        else:
            print(f"  ✓ 期待値と一致（許容誤差内）")
    
    # STOP0の場合の特別チェック
    elif strategy == "stop0":
        expected_total = 0.0  # 100% cash
        print(f"  [STOP0期待値] total={expected_total} (100% cash)")
        total_diff = abs(df_check['total_weight_sum'].mean() - expected_total)
        if total_diff > 0.01:
            print(f"  ⚠ 期待値との差分が大きい: total_diff={total_diff:.6f}")
        else:
            print(f"  ✓ 期待値と一致（許容誤差内）")
    
    # CSVに保存
    output_path = RESEARCH_REPORTS_DIR / f"stop_weights_sanity_{strategy}_w{window}.csv"
    df_check.to_csv(output_path, index=False)
    print(f"  ✓ 検証結果を保存: {output_path}")


if __name__ == "__main__":
    sys.exit(main())

