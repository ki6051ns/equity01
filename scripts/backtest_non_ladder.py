"""
非ラダー版（非重複ウィンドウ方式）のバックテスト
リバランス日をholding_horizonごとに設定し、その間は同じウェイトを保持
"""
from pathlib import Path
from typing import List

import pandas as pd
import numpy as np

from scoring_engine import ScoringEngineConfig, build_daily_portfolio
from event_guard import EventGuard
from weights_cleaning import clean_target_weights


# バックテストモード: "z_lin" / "rank" / "z_clip_rank" / "z_lowvol" / "z_downvol" / "z_downbeta" / "z_downcombo"
BACKTEST_MODE = "z_lin"  # ← "rank" / "z_clip_rank" / "z_lowvol" / "z_downvol" / "z_downbeta" / "z_downcombo" に切り替え可能


def get_score_col_for_horizon(horizon: int) -> str:
    """
    horizon に応じてスコア列を切り替える
    
    Parameters
    ----------
    horizon : int
        投資ホライゾン（5, 10, 20, 60 など）
    
    Returns
    -------
    str
        使用するスコア列名
    """
    if BACKTEST_MODE == "z_lin":
        return "feature_score"  # = score_z_lin
    elif BACKTEST_MODE == "rank":
        return "score_rank_only"
    elif BACKTEST_MODE == "z_clip_rank":
        return "score_z_clip_rank"
    elif BACKTEST_MODE == "z_lowvol":
        return "score_z_lowvol"
    elif BACKTEST_MODE == "z_downvol":
        return "score_z_downvol"
    elif BACKTEST_MODE == "z_downbeta":
        return "score_z_downbeta"
    elif BACKTEST_MODE == "z_downcombo":
        return "score_z_downcombo"
    else:
        raise ValueError(f"Unknown BACKTEST_MODE: {BACKTEST_MODE}")


def get_mode_suffix() -> str:
    """
    BACKTEST_MODE に応じたファイル名サフィックスを返す
    
    Returns
    -------
    str
        ファイル名サフィックス（zlin, rank, zclip, zlowvol）
    """
    if BACKTEST_MODE == "z_lin":
        return "zlin"
    elif BACKTEST_MODE == "rank":
        return "rank"
    elif BACKTEST_MODE == "z_clip_rank":
        return "zclip"
    elif BACKTEST_MODE == "z_lowvol":
        return "zlowvol"
    elif BACKTEST_MODE == "z_downvol":
        return "zdownvol"
    elif BACKTEST_MODE == "z_downbeta":
        return "zdownbeta"
    elif BACKTEST_MODE == "z_downcombo":
        return "zdowncombo"
    else:
        raise ValueError(f"Unknown BACKTEST_MODE: {BACKTEST_MODE}")


def backtest_non_ladder(
    features: pd.DataFrame,
    prices: pd.DataFrame,
    holding_horizon: int,
) -> pd.DataFrame:
    """
    非ラダー版（非重複ウィンドウ方式）でバックテストを実行
    
    リバランス日をholding_horizonごとに設定し、その間は同じウェイトを保持する。
    
    Args:
        features: 全銘柄×営業日の特徴量（daily_feature_scores.parquet）
        prices: 全銘柄×営業日の価格
        holding_horizon: 5, 10, 20, 60 など（保持期間）
    
    Returns:
        日次ポートフォリオリターンのDataFrame
    """
    # EventGuard を初期化
    guard = EventGuard()
    
    # 日付をソート
    features["date"] = pd.to_datetime(features["date"])
    features = features.sort_values("date")
    dates = sorted(features["date"].unique())
    
    # 価格データを準備
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["symbol", "date"])
    
    # 価格データを日付×銘柄のピボットテーブルに変換（高速化のため）
    prices_pivot = prices.pivot_table(
        index="date", 
        columns="symbol", 
        values="close"
    )
    
    # 翌日のリターンを計算（close-to-close）
    prices_ret = prices_pivot.pct_change().shift(-1)
    
    # ポートフォリオ構築用の設定（horizon に応じてスコア列を切り替え）
    score_col = get_score_col_for_horizon(holding_horizon)
    cfg = ScoringEngineConfig(
        score_col=score_col,
    )
    
    # リバランス日を決定（holding_horizon ごと）
    rebalance_dates = []
    last_rebalance_idx = -1
    
    for i, dt in enumerate(dates):
        if i == 0 or (i - last_rebalance_idx) >= holding_horizon:
            rebalance_dates.append(dt)
            last_rebalance_idx = i
    
    print(f"  [H{holding_horizon}] 非ラダー方式バックテスト開始（リバランス日数: {len(rebalance_dates)} 日）")
    
    # 各リバランス日でポートフォリオを構築し、その後の期間のリターンを計算
    rows = []
    current_weights = None  # {symbol: weight} の辞書
    
    for i, rebalance_date in enumerate(rebalance_dates):
        # リバランス日の特徴量を取得
        today_feat = features[features["date"] == rebalance_date].copy()
        
        if today_feat.empty:
            continue
        
        # 決算銘柄を除外
        excluded = guard.get_excluded_symbols(rebalance_date.date())
        if excluded:
            today_feat = today_feat[~today_feat["symbol"].isin(excluded)]
        
        if today_feat.empty:
            continue
        
        # ポートフォリオを構築
        try:
            df_port = build_daily_portfolio(today_feat, cfg)
            
            if df_port.empty:
                continue
            
            # ウェイトをSeriesに変換
            raw_w = pd.Series(
                df_port.set_index("symbol")["weight"],
                name="weight"
            )
            
        except Exception as e:
            if i % 50 == 0:
                print(f"  [H{holding_horizon}] 警告: {rebalance_date} のポートフォリオ構築失敗: {e}")
            continue
        
        # クリーニングレイヤー適用
        if rebalance_date not in prices_pivot.index:
            continue
        
        prices_t = prices_pivot.loc[rebalance_date]
        common_symbols = raw_w.index.intersection(prices_t.index)
        if len(common_symbols) == 0:
            continue
        
        raw_w_aligned = raw_w[common_symbols]
        prices_t_aligned = prices_t[common_symbols]
        
        try:
            clean_w, _ = clean_target_weights(
                raw_w_aligned,
                prices_t_aligned,
                nav=1.0,
                min_abs_weight=0.001,
                max_names_per_side=30,
                lot_size=100,
                use_lot_rounding=True,
            )
        except Exception as e:
            if i % 50 == 0:
                print(f"  [H{holding_horizon}] 警告: {rebalance_date} のクリーニング失敗: {e}")
            continue
        
        # ウェイトを辞書形式に変換
        current_weights = dict(zip(clean_w.index, clean_w.values))
        
        # 次のリバランス日まで（または最後まで）のリターンを計算
        next_rebalance_idx = i + 1
        if next_rebalance_idx < len(rebalance_dates):
            end_date = rebalance_dates[next_rebalance_idx]
            holding_dates = [
                d for d in dates 
                if rebalance_date < d <= end_date
            ]
        else:
            # 最後のリバランス日以降は最後の日まで
            holding_dates = [
                d for d in dates 
                if d > rebalance_date
            ]
        
        # 各日付でポートフォリオリターンを計算
        for trade_date in holding_dates:
            if trade_date not in prices_ret.index:
                continue
            
            # 翌日のリターンを取得
            asset_ret = prices_ret.loc[trade_date]
            
            # ポートフォリオリターンを計算
            port_ret_cc = 0.0
            for symbol, weight in current_weights.items():
                if symbol in asset_ret.index:
                    ret = asset_ret[symbol]
                    if pd.notna(ret):
                        port_ret_cc += weight * ret
            
            rows.append({
                "trade_date": trade_date,
                "port_ret_cc": port_ret_cc,
            })
        
        if (i + 1) % 50 == 0:
            print(f"  [H{holding_horizon}] 進捗: {i + 1}/{len(rebalance_dates)} リバランス日処理完了")
    
    df_result = pd.DataFrame(rows)
    if df_result.empty:
        print(f"  [H{holding_horizon}] 警告: 結果が空です")
        return pd.DataFrame(columns=["trade_date", "port_ret_cc"])
    
    df_result = df_result.sort_values("trade_date").reset_index(drop=True)
    print(f"  [H{holding_horizon}] バックテスト完了: {len(df_result)} 日分のリターンを計算")
    
    return df_result


def main():
    """H=10の非ラダー版バックテストを実行"""
    from horizon_ensemble import build_features_shared, calc_alpha_beta_for_horizon, summarize_horizon, compute_monthly_perf, print_horizon_performance
    
    horizon = 20
    
    print("=" * 60)
    print(f"=== H{horizon} 非ラダー版バックテスト実行 ===")
    print("=" * 60)
    
    # 共有featureと価格データを読み込み
    print("\n[STEP 1] 共有featureと価格データを読み込み中...")
    features, prices = build_features_shared()
    print(f"  Features: {len(features)} rows")
    print(f"  Prices: {len(prices)} rows")
    
    # バックテスト実行
    print(f"\n[STEP 2] H{horizon} 非ラダー版バックテスト実行中...")
    df_pt = backtest_non_ladder(features, prices, horizon)
    # ファイル名にモードを含める（非ラダー版）
    suffix_mode = get_mode_suffix()
    pt_path = Path(f"data/processed/paper_trade_h{horizon}_nonladder_{suffix_mode}.parquet")
    pt_path.parent.mkdir(parents=True, exist_ok=True)
    df_pt.to_parquet(pt_path, index=False)
    print(f"  [H{horizon}] バックテスト完了: {len(df_pt)} 日分")
    
    # 相対α計算
    print(f"  [H{horizon}] 相対α計算中...")
    df_alpha = calc_alpha_beta_for_horizon(df_pt, horizon)
    # 非ラダー版用のファイル名に変更（モードを含める）
    suffix_mode = get_mode_suffix()
    alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{horizon}_nonladder_{suffix_mode}.parquet")
    alpha_path.parent.mkdir(parents=True, exist_ok=True)
    df_alpha.to_parquet(alpha_path, index=False)
    print(f"  [H{horizon}] 相対α計算完了")
    
    # サマリ計算
    print(f"  [H{horizon}] サマリ計算中...")
    summary = summarize_horizon(df_alpha, horizon)
    print(
        f"  [H{horizon}] total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"max_dd={summary['max_drawdown']:.2%}"
    )
    
    # 月次・年次パフォーマンスを計算
    print(f"  [H{horizon}] 月次・年次集計中...")
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=f"nonladder_h{horizon}",
        out_prefix="data/processed/horizon"
    )
    print(f"  [H{horizon}] 月次・年次集計完了")
    
    # パフォーマンス表示
    print_horizon_performance(df_alpha, horizon, monthly, yearly)
    
    print("\n" + "=" * 60)
    print(f"=== H{horizon} 非ラダー版バックテスト完了 ===")
    print("=" * 60)


if __name__ == "__main__":
    main()

