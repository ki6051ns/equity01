#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/generate_variant_weights.py

variant別/horizon別の日次weightsを生成する（追加出力）

入力:
- data/processed/daily_feature_scores.parquet（core生成物）

出力:
- data/processed/weights/h{H}_{ladder}_{variant}.parquet（date, symbol, weight）

weightsの定義は「その日の保有比率」。ロングオンリーなら sum(weight)=1 を原則とし、0/NaN/重複を禁止。

仕様:
- nonladder: horizon間隔でリバランスし、そのweightsをhorizon日ホールド（複製）
- ladder: 毎日weights生成し、直近h本の平均を使用（全営業日のweightsを生成）
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
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/generate_variant_weights.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np
from typing import List
from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio

DATA_DIR = Path("data/processed")
WEIGHTS_DIR = DATA_DIR / "weights"
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_weights_for_variant(
    variant_key: str,
    horizon: int,
    ladder_type: str
) -> pd.DataFrame:
    """
    variant別/horizon別の日次weightsを生成する
    
    Parameters
    ----------
    variant_key : str
        "rank" または "zdownvol"
    horizon : int
        ホライゾン（保持期間）
    ladder_type : str
        "ladder" または "nonladder"
    
    Returns
    -------
    pd.DataFrame
        date, symbol, weight を含むDataFrame
    
    仕様:
    - nonladder: horizon間隔でリバランスし、そのweightsをhorizon日ホールド（複製）
      ※ 例: horizon=5の場合、0, 5, 10, 15日目にリバランスし、それぞれのweightsを5日間ホールド
    - ladder: 毎日weightsを生成し、直近h本の平均を使用（全営業日のweightsを生成）
      ※ 参照: scripts/analysis/horizon_ensemble.py:101-357 (backtest_with_horizon)
    """
    # EventGuardは未完成のため削除（deprecated/2025Q4_pre_weights_fix/に移動）
    # from scripts.core.event_guard import EventGuard
    from scripts.analysis.weights_cleaning import clean_target_weights
    from scripts.tools.lib import data_loader
    
    # 特徴量を読み込む
    feat_path = DATA_DIR / "daily_feature_scores.parquet"
    if not feat_path.exists():
        raise FileNotFoundError(
            f"{feat_path} がありません。先に build_features.py を実行してください。"
        )
    
    df_features = pd.read_parquet(feat_path)
    df_features["date"] = pd.to_datetime(df_features["date"])
    df_features = df_features.sort_values("date")
    
    # variantに応じてスコア列を選択
    if variant_key == "rank":
        score_col = "score_rank_only"
    elif variant_key == "zdownvol":
        # score_z_downvolが存在しない場合はscore_z_linを使用
        if "score_z_downvol" in df_features.columns:
            score_col = "score_z_downvol"
        elif "score_z_lin" in df_features.columns:
            score_col = "score_z_lin"
        else:
            raise ValueError(
                f"スコア列 'score_z_downvol' または 'score_z_lin' が存在しません。"
                f"利用可能な列: {df_features.columns.tolist()}"
            )
    else:
        raise ValueError(f"Unknown variant_key: {variant_key}")
    
    # スコア列が存在するか確認
    if score_col not in df_features.columns:
        raise ValueError(
            f"スコア列 '{score_col}' が存在しません。"
            f"利用可能な列: {df_features.columns.tolist()}"
        )
    
    # ScoringEngineConfigを設定
    config = ScoringEngineConfig()
    config.score_col = score_col
    config.date_col = "date"
    config.size_bucket_col = "size_bucket"
    config.max_names_per_day = 30  # 既存ロジックに合わせる
    config.weighting_scheme = "equal"  # 等ウェイト
    
    # EventGuardは未完成のため削除（deprecated/2025Q4_pre_weights_fix/に移動）
    # guard = EventGuard()
    
    # 価格データを読み込む（ladder方式のクリーニングに必要）
    prices = data_loader.load_prices()
    
    # 【修正】universeに含まれる銘柄のみをフィルタリング（1306.TなどのETF混入防止）
    universe_path = Path("data/intermediate/universe/latest_universe.parquet")
    if universe_path.exists():
        df_universe = pd.read_parquet(universe_path)
        if "ticker" in df_universe.columns:
            universe_tickers = set(df_universe["ticker"].unique())
            prices_before = len(prices)
            prices = prices[prices["symbol"].isin(universe_tickers)].copy()
            prices_after = len(prices)
            excluded = prices_before - prices_after
            if excluded > 0:
                excluded_symbols = set(prices["symbol"].unique()) - universe_tickers if "symbol" in prices.columns else set()
                print(f"[INFO] Universeフィルタリング: {excluded} rows excluded")
                if excluded_symbols:
                    print(f"[INFO] 除外されたsymbol: {sorted(excluded_symbols)}")
        else:
            print(f"[WARN] Universeファイルに'ticker'列がありません。フィルタリングをスキップします。")
    else:
        print(f"[WARN] Universeファイルが見つかりません: {universe_path}。フィルタリングをスキップします。")
    
    prices["date"] = pd.to_datetime(prices["date"])
    prices_pivot = prices.pivot_table(
        index="date",
        columns="symbol",
        values="close"
    )
    
    # 営業日リストを取得（全営業日を含めるため、pricesから取得）
    # ladder方式では全営業日のweightsが必要（維持日も含める）
    all_trade_dates = sorted(prices["date"].unique()) if ladder_type == "ladder" else sorted(df_features["date"].unique())
    
    if ladder_type == "nonladder":
        # 非ラダー方式：horizon間隔でリバランスし、そのweightsをhorizon日ホールド（複製）
        trade_dates = sorted(df_features["date"].unique())
        rows = []
        for i in range(0, len(trade_dates), horizon):
            date = trade_dates[i]
            
            # 当日の特徴量を取得
            today_feat = df_features[df_features["date"] == date].copy()
            if today_feat.empty:
                continue
            
            # EventGuardは未完成のため決算除外機能を削除（deprecated/2025Q4_pre_weights_fix/に移動）
            # excluded = guard.get_excluded_symbols(date.date())
            # if excluded:
            #     today_feat = today_feat[~today_feat["symbol"].isin(excluded)]
            
            if today_feat.empty:
                continue
            
            # ポートフォリオを構築
            try:
                df_port = build_daily_portfolio(today_feat, config)
                if df_port.empty:
                    continue
                
                # weightsを取得
                weights_series = df_port.set_index("symbol")["weight"]
                
                # クリーニング（既存ロジックに合わせる）
                if date in prices_pivot.index:
                    prices_t = prices_pivot.loc[date]
                    common_symbols = weights_series.index.intersection(prices_t.index)
                    if len(common_symbols) > 0:
                        weights_aligned = weights_series[common_symbols]
                        prices_t_aligned = prices_t[common_symbols]
                        try:
                            clean_w, _ = clean_target_weights(
                                weights_aligned,
                                prices_t_aligned,
                                nav=1.0,
                                min_abs_weight=0.001,
                                max_names_per_side=30,
                                lot_size=100,
                                use_lot_rounding=True,
                            )
                            weights_series = clean_w
                        except Exception:
                            pass  # クリーニング失敗時は元のweightsを使用
                
                # 正規化
                if weights_series.sum() > 0:
                    weights_series = weights_series / weights_series.sum()
                
                # 次のhorizon日まで同じweightsを使用
                for j in range(i, min(i + horizon, len(trade_dates))):
                    target_date = trade_dates[j]
                    for symbol, weight in weights_series.items():
                        rows.append({
                            "date": target_date,
                            "symbol": symbol,
                            "weight": weight,
                        })
            except Exception as e:
                print(f"  [WARN] {date} のポートフォリオ構築失敗: {e}")
                continue
        
        df_weights = pd.DataFrame(rows)
        
    else:  # ladder_type == "ladder"
        # ラダー方式：毎日weightsを生成し、過去horizon本の平均を使用
        # 参照: scripts/analysis/horizon_ensemble.py:101-357
        
        # 全営業日のリストを取得（weightsファイルに全営業日を含めるため）
        trade_dates = sorted(prices["date"].unique())
        
        # 過去horizon本のclean weightsを保存するキュー
        last_weights: List[pd.Series] = []
        
        rows = []
        
        for date in trade_dates:
            # 当日の特徴量を取得
            today_feat = df_features[df_features["date"] == date].copy()
            
            # データがない日でも、キューがあれば前回weightsを維持
            if today_feat.empty:
                # キューから前回weightsを計算
                if len(last_weights) > 0:
                    # キュー内の平均を計算
                    all_symbols = set()
                    for w in last_weights:
                        all_symbols.update(w.index)
                    
                    weights_aligned = []
                    for w in last_weights:
                        w_expanded = pd.Series(0.0, index=sorted(all_symbols))
                        w_expanded[w.index] = w
                        weights_aligned.append(w_expanded)
                    
                    w_today = sum(weights_aligned) / len(weights_aligned)
                    
                    # 正規化（保険的に）
                    if w_today.sum() > 0:
                        w_today = w_today / w_today.sum()
                    
                    # 出力
                    for symbol, weight in w_today.items():
                        rows.append({
                            "date": date,
                            "symbol": symbol,
                            "weight": weight,
                        })
                continue
            
            # EventGuardは未完成のため決算除外機能を削除（deprecated/2025Q4_pre_weights_fix/に移動）
            # excluded = guard.get_excluded_symbols(date.date())
            # if excluded:
            #     today_feat = today_feat[~today_feat["symbol"].isin(excluded)]
            
            if today_feat.empty:
                # 決算除外後も空の場合は、キューがあれば前回weightsを維持
                if len(last_weights) > 0:
                    all_symbols = set()
                    for w in last_weights:
                        all_symbols.update(w.index)
                    
                    weights_aligned = []
                    for w in last_weights:
                        w_expanded = pd.Series(0.0, index=sorted(all_symbols))
                        w_expanded[w.index] = w
                        weights_aligned.append(w_expanded)
                    
                    w_today = sum(weights_aligned) / len(weights_aligned)
                    
                    if w_today.sum() > 0:
                        w_today = w_today / w_today.sum()
                    
                    for symbol, weight in w_today.items():
                        rows.append({
                            "date": date,
                            "symbol": symbol,
                            "weight": weight,
                        })
                continue
            
            # ポートフォリオを構築
            try:
                df_port = build_daily_portfolio(today_feat, config)
                if df_port.empty:
                    continue
                
                # weightsを取得
                raw_w = pd.Series(
                    df_port.set_index("symbol")["weight"],
                    name="weight"
                )
                
                # クリーニング（既存ロジックに合わせる）
                if date in prices_pivot.index:
                    prices_t = prices_pivot.loc[date]
                    common_symbols = raw_w.index.intersection(prices_t.index)
                    if len(common_symbols) > 0:
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
                            raw_w = clean_w
                        except Exception:
                            pass  # クリーニング失敗時は元のweightsを使用
                
                # 正規化
                if raw_w.sum() > 0:
                    raw_w = raw_w / raw_w.sum()
                
                # キューに追加（最大horizon本）
                last_weights.append(raw_w)
                if len(last_weights) > horizon:
                    last_weights.pop(0)
                
                # キュー内の平均を当日weightsとする
                if len(last_weights) == 0:
                    continue
                
                # キュー内の全ウェイトを平均（インデックスを揃える）
                all_symbols = set()
                for w in last_weights:
                    all_symbols.update(w.index)
                
                weights_aligned = []
                for w in last_weights:
                    w_expanded = pd.Series(0.0, index=sorted(all_symbols))
                    w_expanded[w.index] = w
                    weights_aligned.append(w_expanded)
                
                w_today = sum(weights_aligned) / len(weights_aligned)
                
                # 正規化（保険的に）
                if w_today.sum() > 0:
                    w_today = w_today / w_today.sum()
                
                # 出力
                for symbol, weight in w_today.items():
                    rows.append({
                        "date": date,
                        "symbol": symbol,
                        "weight": weight,
                    })
            except Exception as e:
                print(f"  [WARN] {date} のポートフォリオ構築失敗: {e}")
                continue
        
        df_weights = pd.DataFrame(rows)
    
    # 日付ごとに正規化（保険的に）
    df_weights = df_weights.groupby("date", group_keys=False).apply(
        lambda g: g.assign(weight=g["weight"] / g["weight"].sum() if g["weight"].sum() > 0 else 0.0)
    )
    
    df_weights = df_weights.sort_values(["date", "symbol"]).reset_index(drop=True)
    
    return df_weights


def main():
    """メイン関数（テスト用）"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="variant別/horizon別の日次weightsを生成"
    )
    parser.add_argument(
        "--variant",
        type=str,
        required=True,
        choices=["rank", "zdownvol"],
        help="variant（rank または zdownvol）"
    )
    parser.add_argument(
        "--horizon",
        type=int,
        required=True,
        help="ホライゾン"
    )
    parser.add_argument(
        "--ladder",
        type=str,
        required=True,
        choices=["ladder", "nonladder"],
        help="ladder方式かどうか"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力ファイルパス（指定しない場合は自動生成）"
    )
    
    args = parser.parse_args()
    
    # weightsを生成
    print(f"[{args.variant}] H{args.horizon} ({args.ladder}) weightsを生成中...")
    df_weights = generate_weights_for_variant(args.variant, args.horizon, args.ladder)
    
    # 出力パス
    if args.output:
        output_path = Path(args.output)
    else:
        suffix = "rank_only" if args.variant == "rank" else "zdownvol"
        output_path = WEIGHTS_DIR / f"h{args.horizon}_{args.ladder}_{suffix}.parquet"
    
    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_weights.to_parquet(output_path, index=False)
    print(f"✓ 保存: {output_path}")
    print(f"  日数: {df_weights['date'].nunique()}")
    print(f"  最終日のweight合計: {df_weights[df_weights['date'] == df_weights['date'].max()]['weight'].sum():.6f}")


if __name__ == "__main__":
    main()

