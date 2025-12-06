"""
horizon_ensemble.py

複数の投資ホライゾン（5, 10, 20, 60日）でバックテストを実行し、
等ウェイトでアンサンブルする。

feature_builder.py は変更せず、投資ホライゾンの違いは
リバランス頻度で吸収する。
"""
from pathlib import Path
from typing import List, Tuple, Dict

import pandas as pd
import numpy as np

from scoring_engine import ScoringEngineConfig, build_daily_portfolio
from event_guard import EventGuard
from weights_cleaning import clean_target_weights
import data_loader


def build_features_shared() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    共有 feature を一度だけ構築（既存の build_features.py の出力を利用）
    """
    feat_path = Path("data/processed/daily_feature_scores.parquet")
    if not feat_path.exists():
        raise FileNotFoundError(
            f"{feat_path} がありません。先に build_features.py を実行してください。"
        )
    
    df_feat = pd.read_parquet(feat_path)
    df_prices = data_loader.load_prices()
    
    return df_feat, df_prices


def backtest_with_horizon(
    features: pd.DataFrame,
    prices: pd.DataFrame,
    holding_horizon: int,
) -> pd.DataFrame:
    """
    ラダー方式でバックテストを実行（ウィンドウ重複方式）
    
    毎営業日で新しい「チケット」を発行し、それを h 営業日保持するラダー方式。
    任意の horizon h に対して、日次のターゲットウェイトは
    「直近 h 本のターゲットウェイトの平均」で構成する。
    
    Args:
        features: 全銘柄×営業日の特徴量（daily_feature_scores.parquet）
        prices: 全銘柄×営業日の価格
        holding_horizon: 1, 5, 10, 20, 60 など（保持期間）
    
    Returns:
        日次ポートフォリオリターンのDataFrame
    """
    # EventGuard を初期化
    guard = EventGuard()
    
    # 日付をソート
    features["date"] = pd.to_datetime(features["date"])
    features = features.sort_values("date")
    trade_dates = sorted(features["date"].unique())
    
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
    
    # ポートフォリオ構築用の設定
    cfg = ScoringEngineConfig()
    
    # 過去 h 本の clean_w を保存するキュー
    last_weights: List[pd.Series] = []
    
    rows = []
    
    print(f"  [H{holding_horizon}] ラダー方式バックテスト開始（全営業日: {len(trade_dates)} 日）")
    
    for t_idx, t in enumerate(trade_dates[:-1]):  # t のウェイトで (t+1) のリターンを取る前提
        # 1) 当日の signal / features から raw weight を構築
        today_feat = features[features["date"] == t].copy()
        
        if today_feat.empty:
            continue
        
        # 決算銘柄を除外
        excluded = guard.get_excluded_symbols(t.date())
        if excluded:
            today_feat = today_feat[~today_feat["symbol"].isin(excluded)]
        
        if today_feat.empty:
            continue
        
        # ポートフォリオを構築
        try:
            df_port = build_daily_portfolio(today_feat, cfg)
            
            if df_port.empty:
                if t_idx < 3:
                    print(f"  [DEBUG][H{holding_horizon}][{t}] df_port is empty")
                continue
            
            # ウェイトをSeriesに変換
            raw_w = pd.Series(
                df_port.set_index("symbol")["weight"],
                name="weight"
            )
            
            # DEBUG: raw_wの統計情報（最初の3日間）
            if t_idx < 3:
                raw_sum = raw_w.sum()
                raw_pos_sum = raw_w[raw_w > 0].sum()
                raw_neg_sum = raw_w[raw_w < 0].sum()
                raw_non_zero = (raw_w != 0).sum()
                raw_max_abs = raw_w.abs().max()
                print(f"  [DEBUG][H{holding_horizon}][{t}] raw_w: sum={raw_sum:.6f}, "
                      f"pos_sum={raw_pos_sum:.6f}, neg_sum={raw_neg_sum:.6f}, "
                      f"non_zero_count={raw_non_zero}, len={len(raw_w)}, max_abs={raw_max_abs:.6f}")
                if raw_non_zero > 0:
                    print(f"  [DEBUG] raw_w top5 abs:")
                    top5 = raw_w.reindex(raw_w.abs().sort_values(ascending=False).index[:5])
                    print(f"    {top5}")
            
        except Exception as e:
            if t_idx < 3 or t_idx % 500 == 0:
                print(f"  [H{holding_horizon}] 警告: {t} のポートフォリオ構築失敗: {e}")
            continue
        
        # 2) クリーニングレイヤー適用
        # 当日の価格を取得
        if t not in prices_pivot.index:
            continue
        
        prices_t = prices_pivot.loc[t]
        # raw_wとprices_tのインデックス（symbol）を揃える
        common_symbols = raw_w.index.intersection(prices_t.index)
        if len(common_symbols) == 0:
            continue
        
        raw_w_aligned = raw_w[common_symbols]
        prices_t_aligned = prices_t[common_symbols]
        
        try:
            clean_w, shares = clean_target_weights(
                raw_w_aligned,
                prices_t_aligned,
                nav=1.0,
                min_abs_weight=0.001,  # 0.1%に緩和（デバッグ用）
                max_names_per_side=30,
                lot_size=100,
                use_lot_rounding=True,
            )
            
            # DEBUG: クリーニング前後の比較
            if t_idx < 3:
                print(f"  [DEBUG][H{holding_horizon}][{t}] after cleaning: "
                      f"raw_sum={raw_w_aligned.sum():.6f}, "
                      f"clean_sum={clean_w.sum():.6f}, "
                      f"clean_non_zero={(clean_w != 0).sum()}")
            
        except Exception as e:
            if t_idx < 3 or t_idx % 500 == 0:
                print(f"  [H{holding_horizon}] 警告: {t} のクリーニング失敗: {e}")
                if t_idx < 3:
                    import traceback
                    traceback.print_exc()
            continue
        
        # DEBUG: 最初の3日間だけログ出力（実行時間短縮のため）
        if t_idx < 3:
            sum_w = clean_w.sum()
            pos_sum = clean_w[clean_w > 0].sum()
            neg_sum = clean_w[clean_w < 0].sum()
            print(f"  [DEBUG][H{holding_horizon}][{t}] sum_w={sum_w:.6f}, "
                  f"pos_sum={pos_sum:.6f}, neg_sum={neg_sum:.6f}, "
                  f"non_zero_count={(clean_w != 0).sum()}")
        
        # 3) キューに追加（最大 horizon 本）
        last_weights.append(clean_w)
        if len(last_weights) > holding_horizon:
            last_weights.pop(0)
        
        # 4) キュー内の平均を当日ポートフォリオとする
        #    (開始直後は len(last_weights) < horizon なので、その時点での平均)
        if len(last_weights) == 0:
            continue
        
        # キュー内の全ウェイトを平均（インデックスを揃える）
        # インデックスを統一するために、全銘柄のユニオンを取る
        all_symbols = set()
        for w in last_weights:
            all_symbols.update(w.index)
        
        # 各ウェイトを全銘柄に拡張（存在しない銘柄は0）
        weights_aligned = []
        for w in last_weights:
            w_expanded = pd.Series(0.0, index=sorted(all_symbols))
            w_expanded[w.index] = w
            weights_aligned.append(w_expanded)
        
        w_today = sum(weights_aligned) / len(weights_aligned)
        
        # DEBUG: w_todayが全部ゼロでないか確認
        if t_idx < 3:
            w_sum = w_today.sum()
            w_pos_sum = w_today[w_today > 0].sum()
            w_neg_sum = w_today[w_today < 0].sum()
            print(f"  [DEBUG][H{holding_horizon}][{t}] w_today: sum={w_sum:.6f}, "
                  f"pos_sum={w_pos_sum:.6f}, neg_sum={w_neg_sum:.6f}, "
                  f"non_zero_count={(w_today != 0).sum()}")
        
        # 5) 翌営業日のリターンを使って PnL を計算
        next_date = trade_dates[t_idx + 1]
        
        if next_date not in prices_ret.index:
            continue
        
        # 翌日のリターンを取得
        asset_ret = prices_ret.loc[next_date]
        
        # DEBUG: 最初の1回だけasset_retのサンプルを表示
        if t_idx == 0:
            print(f"  [DEBUG][H{holding_horizon}] asset_ret example (first 5):")
            print(f"    {asset_ret.head()}")
            print(f"  [DEBUG][H{holding_horizon}] w_today example (non-zero, first 5):")
            w_nonzero = w_today[w_today != 0]
            if len(w_nonzero) > 0:
                print(f"    {w_nonzero.head()}")
            else:
                print(f"    (all zero)")
        
        # インデックスを揃える
        common_symbols_ret = w_today.index.intersection(asset_ret.index)
        if len(common_symbols_ret) == 0:
            continue
        
        w_today_aligned = w_today[common_symbols_ret]
        asset_ret_aligned = asset_ret[common_symbols_ret]
        
        # NaNを0に置換（安全のため）
        w_today_aligned = w_today_aligned.fillna(0.0)
        asset_ret_aligned = asset_ret_aligned.fillna(0.0)
        
        # ポートフォリオリターンを計算
        port_ret_cc = float((w_today_aligned * asset_ret_aligned).sum())
        
        # DEBUG: 最初の1回だけport_ret_ccを表示
        if t_idx == 0:
            print(f"  [DEBUG][H{holding_horizon}] port_ret_cc example: {port_ret_cc:.6f}")
        
        rows.append({
            "trade_date": next_date,
            "port_ret_cc": port_ret_cc,
        })
        
        if (t_idx + 1) % 500 == 0:
            print(f"  [H{holding_horizon}] 進捗: {t_idx + 1}/{len(trade_dates) - 1} 日処理完了")
        elif (t_idx + 1) % 100 == 0:
            print(f"  [H{holding_horizon}] 進捗: {t_idx + 1}/{len(trade_dates) - 1} 日...")
    
    df = pd.DataFrame(rows)
    if df.empty:
        print(f"  [H{holding_horizon}] 警告: 結果が空です")
        return pd.DataFrame(columns=["trade_date", "port_ret_cc"])
    
    df = df.sort_values("trade_date").reset_index(drop=True)
    print(f"  [H{holding_horizon}] バックテスト完了: {len(df)} 日分のリターンを計算")
    
    # DEBUG: 最終的なデバッグ情報を出力
    if len(df) > 0:
        print(f"  [DEBUG][H{holding_horizon}] port_ret_cc describe:")
        print(f"    {df['port_ret_cc'].describe()}")
        print(f"  [DEBUG][H{holding_horizon}] head (first 5 rows):")
        print(f"    {df[['trade_date', 'port_ret_cc']].head()}")
        print(f"  [DEBUG][H{holding_horizon}] port_ret_cc stats:")
        print(f"    mean={df['port_ret_cc'].mean():.6f}, std={df['port_ret_cc'].std():.6f}, "
              f"min={df['port_ret_cc'].min():.6f}, max={df['port_ret_cc'].max():.6f}")
        print(f"    zero_count={(df['port_ret_cc'] == 0).sum()}/{len(df)}")
    
    return df


def summarize_horizon(df_alpha: pd.DataFrame, horizon: int) -> dict:
    """
    ホライゾン別サマリを計算
    
    Args:
        df_alpha: paper_trade_with_alpha_beta_h{h}.parquet 相当
            - trade_date
            - port_ret_cc
            - tpx_ret_cc
            - rel_alpha_daily
            - ほか cum_系
    
    Returns:
        サマリ情報の辞書
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    # ドローダウン計算
    if "cum_port" in df.columns:
        cum_port = df["cum_port"]
    else:
        cum_port = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cum_port.cummax()
    drawdown = (cum_port / rolling_max - 1.0).min()
    
    return {
        "horizon": horizon,
        "start": df["trade_date"].min(),
        "end": df["trade_date"].max(),
        "days": len(df),
        "total_port": total_port,
        "total_tpx": total_tpx,
        "total_alpha": total_alpha,
        "alpha_mean_daily": mean_alpha,
        "alpha_std_daily": std_alpha,
        "alpha_sharpe_annual": sharpe_alpha,
        "max_drawdown": drawdown,
    }


def compute_monthly_perf(df_alpha: pd.DataFrame, label: str, out_prefix: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    月次・年次パフォーマンスを計算（既存のmonthly_performance.pyのロジックを流用）
    
    Args:
        df_alpha: paper_trade_with_alpha_beta 相当のDataFrame
        label: ラベル（例: "h5", "h10"）
        out_prefix: 出力ファイルのプレフィックス
    
    Returns:
        (monthly_returns, yearly_returns) のタプル
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
        .reset_index()
    )
    
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
                "rel_alpha": "sum",  # 月次相対αの累積（簡易版）
                "days": "sum",
            }
        )
        .reset_index()
    )
    yearly["rel_alpha"] = yearly["port_return"] - yearly["tpx_return"]  # 正確な年次相対α
    
    # 保存
    monthly_path = Path(f"{out_prefix}_monthly_{label}.parquet")
    monthly_path.parent.mkdir(parents=True, exist_ok=True)
    monthly_returns.to_parquet(monthly_path, index=False)
    
    yearly_path = Path(f"{out_prefix}_yearly_{label}.parquet")
    yearly.to_parquet(yearly_path, index=False)
    
    return monthly_returns, yearly


def calc_alpha_beta_for_horizon(df_pt: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    相対α計算（既存 calc_alpha_beta ロジックを DF 版で呼ぶ）
    """
    # TOPIXデータを読み込み
    tpx_path = Path("data/processed/index_tpx_daily.parquet")
    if not tpx_path.exists():
        raise FileNotFoundError(
            f"{tpx_path} がありません。先に build_index_tpx_daily.py を実行してください。"
        )
    
    df_tpx = pd.read_parquet(tpx_path)
    df_tpx = df_tpx.sort_values("trade_date").reset_index(drop=True)
    
    # マージ
    df_pt["trade_date"] = pd.to_datetime(df_pt["trade_date"])
    df = df_pt.merge(
        df_tpx[["trade_date", "tpx_ret_cc"]],
        on="trade_date",
        how="inner"
    )
    
    # 相対αを計算
    df["rel_alpha_daily"] = df["port_ret_cc"] - df["tpx_ret_cc"]
    df["cum_port"] = (1.0 + df["port_ret_cc"]).cumprod()
    df["cum_tpx"] = (1.0 + df["tpx_ret_cc"]).cumprod()
    
    # 保存
    if horizon > 0:
        out_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{horizon}.parquet")
    else:
        out_path = Path("data/processed/paper_trade_with_alpha_beta_ensemble.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    
    return df


def ensemble_horizons(horizons: List[int]) -> pd.DataFrame:
    """
    アンサンブル（等ウェイト）
    """
    dfs = []
    for h in horizons:
        path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}.parquet")
        if not path.exists():
            raise FileNotFoundError(
                f"{path} がありません。先に各ホライゾンのバックテストを実行してください。"
            )
        
        df = pd.read_parquet(path)
        df = df[["trade_date", "port_ret_cc", "rel_alpha_daily"]].copy()
        df = df.rename(columns={
            "port_ret_cc": f"port_ret_cc_h{h}",
            "rel_alpha_daily": f"rel_alpha_h{h}",
        })
        dfs.append(df)
    
    # 日付でマージ
    from functools import reduce
    df_merged = reduce(
        lambda l, r: pd.merge(l, r, on="trade_date", how="inner"),
        dfs
    )
    
    # 等ウェイト合成
    port_cols = [f"port_ret_cc_h{h}" for h in horizons]
    alpha_cols = [f"rel_alpha_h{h}" for h in horizons]
    
    df_merged["port_ret_cc_ens"] = df_merged[port_cols].mean(axis=1)
    df_merged["rel_alpha_ens"] = df_merged[alpha_cols].mean(axis=1)
    
    # 累積リターンも計算
    df_merged["cum_port_ens"] = (1.0 + df_merged["port_ret_cc_ens"]).cumprod()
    
    # TOPIXの累積リターンも追加（最初のホライゾンから取得）
    if "tpx_ret_cc" not in df_merged.columns:
        df_first = pd.read_parquet(f"data/processed/paper_trade_with_alpha_beta_h{horizons[0]}.parquet")
        df_first = df_first[["trade_date", "tpx_ret_cc"]].copy()
        df_merged = df_merged.merge(df_first, on="trade_date", how="left")
    
    df_merged["cum_tpx"] = (1.0 + df_merged["tpx_ret_cc"]).cumprod()
    
    # 保存
    out_path = Path("data/processed/horizon_ensemble.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_merged.to_parquet(out_path, index=False)
    
    return df_merged


def print_horizon_performance(
    df_alpha: pd.DataFrame,
    horizon: int,
    monthly_returns: pd.DataFrame,
    yearly: pd.DataFrame,
) -> None:
    """
    ホライゾン別パフォーマンスを表示（月次・年次・統計を含む）
    """
    df = df_alpha.copy()
    df = df.sort_values("trade_date")
    
    # 累積パフォーマンス
    total_port = (1 + df["port_ret_cc"]).prod() - 1
    total_tpx = (1 + df["tpx_ret_cc"]).prod() - 1
    total_alpha = total_port - total_tpx
    
    # 日次統計
    mean_alpha = df["rel_alpha_daily"].mean()
    std_alpha = df["rel_alpha_daily"].std()
    sharpe_alpha = mean_alpha / std_alpha * (252 ** 0.5) if std_alpha > 0 else float("nan")
    
    # ドローダウン
    cum_port = (1.0 + df["port_ret_cc"]).cumprod()
    rolling_max = cum_port.cummax()
    drawdown = (cum_port / rolling_max - 1.0).min()
    
    # タイトル
    if horizon == 0:
        print(f"\n=== Ensemble Performance ===")
    else:
        print(f"\n=== H{horizon} Performance ===")
    
    print(f"累積: Port {total_port:+.2%}, TOPIX {total_tpx:+.2%}, α {total_alpha:+.2%}")
    print(f"Sharpe(α): {sharpe_alpha:.2f}")
    print(f"maxDD: {drawdown:+.2%}")
    print(f"期間: {df['trade_date'].min()} ～ {df['trade_date'].max()}")
    print(f"日数: {len(df)}")
    
    # 月次リターン表
    print("\n【月次リターン】")
    try:
        pivot_monthly = monthly_returns.pivot_table(
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
        print(monthly_returns[["year", "month", "port_return", "tpx_return", "rel_alpha"]].to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次リターン表
    print("\n【年次リターン】")
    yearly_display = yearly[["year", "port_return", "tpx_return", "rel_alpha"]].copy()
    print(yearly_display.to_string(index=False, float_format="{:+.2%}".format))
    
    # 年次統計
    print("\n【年次統計】")
    yearly_port_mean = yearly["port_return"].mean()
    yearly_tpx_mean = yearly["tpx_return"].mean()
    yearly_alpha_mean = yearly["rel_alpha"].mean()
    yearly_alpha_std = yearly["rel_alpha"].std()
    yearly_alpha_sharpe = yearly_alpha_mean / yearly_alpha_std if yearly_alpha_std > 0 else float("nan")
    yearly_win_rate = (yearly["rel_alpha"] > 0).mean()
    
    print(f"年率平均（Port）: {yearly_port_mean:+.4%}")
    print(f"年率平均（TOPIX）: {yearly_tpx_mean:+.4%}")
    print(f"年率平均（α）: {yearly_alpha_mean:+.4%}")
    print(f"年率標準偏差（α）: {yearly_alpha_std:+.4%}")
    print(f"年率αシャープ: {yearly_alpha_sharpe:+.4f}")
    print(f"年間勝率: {yearly_win_rate:+.2%}")


def print_h1_statistics(df_alpha: pd.DataFrame) -> None:
    """
    H1バックテストの統計情報を表示
    """
    df = df_alpha.copy()
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
            df_pt = pd.read_parquet(paper_trade_path)
            df_pt = df_pt.sort_values("trade_date")
            
            # 日付でマージ
            df_merged = df[["trade_date", "port_ret_cc"]].merge(
                df_pt[["trade_date", "port_ret_cc"]],
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


def run_horizon_ensemble(horizons: List[int] = [1, 5, 10, 20, 60], debug_h1_only: bool = False) -> None:
    """
    全体実行
    """
    print("=" * 60)
    if debug_h1_only:
        print("=== Horizon Ensemble (H1 Debug Mode) ===")
    else:
        print("=== Horizon Ensemble Start ===")
    print("=" * 60)
    
    # デバッグモードの場合はH1のみ
    if debug_h1_only:
        horizons = [1]
        print("デバッグモード: H1のみ実行します")
    
    # 1. shared feature & price load
    print("\n[STEP 1] 共有featureと価格データを読み込み中...")
    features, prices = build_features_shared()
    print(f"  Features: {len(features)} rows")
    print(f"  Prices: {len(prices)} rows")
    
    # 2. horizon別バックテスト
    summary_rows = []
    
    for h in horizons:
        print(f"\n[STEP 2-{h}] H{h} バックテスト実行中...")
        try:
            df_pt = backtest_with_horizon(features, prices, h)
            pt_path = Path(f"data/processed/paper_trade_h{h}.parquet")
            pt_path.parent.mkdir(parents=True, exist_ok=True)
            df_pt.to_parquet(pt_path, index=False)
            print(f"  [H{h}] バックテスト完了: {len(df_pt)} 日分")
            
            print(f"  [H{h}] 相対α計算中...")
            df_alpha = calc_alpha_beta_for_horizon(df_pt, h)
            print(f"  [H{h}] 相対α計算完了")
            
            # H1の場合は統計情報を表示
            if h == 1:
                print_h1_statistics(df_alpha)
            
            # デバッグモードの場合はH1のみで終了
            if debug_h1_only and h == 1:
                print("\n" + "=" * 60)
                print("=== H1 Debug Mode 完了 ===")
                print("=" * 60)
                return
            
            # ホライゾン別サマリを計算
            print(f"  [H{h}] サマリ計算中...")
            summary = summarize_horizon(df_alpha, h)
            summary_rows.append(summary)
            print(
                f"  [H{h}] total_port={summary['total_port']:.2%}, "
                f"total_alpha={summary['total_alpha']:.2%}, "
                f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
                f"max_dd={summary['max_drawdown']:.2%}"
            )
            
            # 月次・年次パフォーマンスを計算
            print(f"  [H{h}] 月次・年次集計中...")
            monthly, yearly = compute_monthly_perf(
                df_alpha,
                label=f"H{h}",
                out_prefix="data/processed/horizon"
            )
            print(f"  [H{h}] 月次・年次集計完了")
            
            # ホライゾン別パフォーマンス表示
            print_horizon_performance(df_alpha, h, monthly, yearly)
            
        except Exception as e:
            print(f"  [H{h}] エラー: {e}")
            raise
    
    # ホライゾン別サマリを保存
    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        summary_path = Path("data/processed/horizon_perf_summary.parquet")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        df_summary.to_parquet(summary_path, index=False)
        
        print("\n=== ホライゾン別パフォーマンスサマリ ===")
        # 表示用にフォーマット
        display_cols = ["horizon", "days", "total_port", "total_tpx", "total_alpha", 
                       "alpha_sharpe_annual", "max_drawdown"]
        display_df = df_summary[display_cols].copy()
        # パーセンテージ列をフォーマット
        for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
        print(display_df.to_string(index=False))
        print(f"\n✓ サマリ保存先: {summary_path}")
    
    # 3. アンサンブル
    print("\n[STEP 3] ホライゾンアンサンブル実行中...")
    df_ens = ensemble_horizons(horizons)
    print(f"  アンサンブル完了: {len(df_ens)} 日分")
    
    # アンサンブル版の相対αを計算（既にensemble_horizonsで計算済み）
    # ただし、calc_alpha_beta_for_horizonの形式に合わせる
    df_ens_alpha = df_ens[["trade_date", "port_ret_cc_ens", "rel_alpha_ens", "tpx_ret_cc", "cum_port_ens", "cum_tpx"]].copy()
    df_ens_alpha = df_ens_alpha.rename(columns={
        "port_ret_cc_ens": "port_ret_cc",
        "rel_alpha_ens": "rel_alpha_daily",
        "cum_port_ens": "cum_port"
    })
    
    # アンサンブル版の月次・年次集計
    print("  アンサンブル版の月次・年次集計中...")
    ensemble_monthly, ensemble_yearly = compute_monthly_perf(
        df_ens_alpha,
        label="ensemble",
        out_prefix="data/processed/horizon"
    )
    
    # アンサンブル版のパフォーマンス表示
    horizon_str = ",".join([f"H{h}" for h in horizons])
    print(f"\n=== Ensemble ({horizon_str}) Performance ===")
    print_horizon_performance(df_ens_alpha, 0, ensemble_monthly, ensemble_yearly)
    
    # アンサンブル版の年率シャープレシオ（総合）を計算
    ret = df_ens_alpha["port_ret_cc"]
    mu_daily = ret.mean()
    sigma_daily = ret.std()
    sharpe_annual = (mu_daily * 252) / (sigma_daily * np.sqrt(252)) if sigma_daily > 0 else float("nan")
    print(f"\nEnsemble annual Sharpe (total): {sharpe_annual:.4f}")
    
    print(f"\n✓ 保存先: data/processed/horizon_ensemble.parquet")
    print("=" * 60)
    print("=== Horizon Ensemble Done ===")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    # コマンドライン引数でデバッグモードを指定可能
    debug_mode = "--debug-h1" in sys.argv
    if debug_mode:
        run_horizon_ensemble(horizons=[1], debug_h1_only=True)
    else:
        run_horizon_ensemble(horizons=[1, 5, 10, 20, 60])

