#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/build_regime_hmm.py

HMM レジームクラスタリング実装

equity01（cross4）の日次αに基づく「quant弱レジーム」をHMMでクラスタリングする。
出力は「日次レジームラベル」および「レジーム別統計」。

戦略内部では使わず、prod側のモニタリング用途のみ。
"""

import sys
from pathlib import Path
import json

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import numpy as np

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    print("[ERROR] hmmlearn がインストールされていません。")
    print("インストール方法: pip install hmmlearn")
    sys.exit(1)

DATA_DIR = Path("data/processed")


def load_alpha_series() -> pd.DataFrame:
    """
    alpha_series.parquet を読み込む
    
    Returns
    -------
    pd.DataFrame
        date, alpha を含むDataFrame
    """
    alpha_path = DATA_DIR / "alpha_series.parquet"
    
    if not alpha_path.exists():
        # フォールバック: cross4から直接計算
        print(f"[WARN] {alpha_path} が見つかりません。cross4から直接計算します...")
        cross4_path = DATA_DIR / "horizon_ensemble_variant_cross4.parquet"
        if not cross4_path.exists():
            raise FileNotFoundError(
                f"{alpha_path} と {cross4_path} の両方が見つかりません。"
                "先に ensemble_variant_cross4.py を実行してください。"
            )
        
        df_cross4 = pd.read_parquet(cross4_path)
        if "rel_alpha_daily" in df_cross4.columns:
            df = pd.DataFrame({
                "date": pd.to_datetime(df_cross4["trade_date"]),
                "alpha": df_cross4["rel_alpha_daily"],
            })
        elif "port_ret_cc" in df_cross4.columns and "tpx_ret_cc" in df_cross4.columns:
            df = pd.DataFrame({
                "date": pd.to_datetime(df_cross4["trade_date"]),
                "alpha": df_cross4["port_ret_cc"] - df_cross4["tpx_ret_cc"],
            })
        else:
            raise ValueError(f"alpha列が見つかりません: {df_cross4.columns.tolist()}")
        
        print(f"[INFO] cross4からalphaを計算: {len(df)} 日分")
        return df
    
    df = pd.read_parquet(alpha_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    print(f"[INFO] Loaded alpha_series from {alpha_path}: {len(df)} 日分")
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    特徴量を計算
    
    Parameters
    ----------
    df : pd.DataFrame
        date, alpha を含むDataFrame
    
    Returns
    -------
    pd.DataFrame
        特徴量を追加したDataFrame
    """
    df = df.copy()
    
    # roll_alpha_mean_63: 63日ローリング平均
    df['roll_alpha_mean_63'] = df['alpha'].rolling(63, min_periods=1).mean()
    
    # roll_alpha_vol_63: 63日ローリング標準偏差
    df['roll_alpha_vol_63'] = df['alpha'].rolling(63, min_periods=1).std()
    
    # dd_252: 過去252日のドローダウン
    cum = (1 + df['alpha']).cumprod()
    roll_max = cum.rolling(252, min_periods=1).max()
    df['dd_252'] = (cum / roll_max - 1).fillna(0)
    
    return df


def fit_hmm(X_scaled: np.ndarray, n_components: int = 3) -> tuple:
    """
    HMMモデルを学習し、レジームを予測
    
    Parameters
    ----------
    X_scaled : np.ndarray
        標準化された特徴量行列
    n_components : int
        状態数（デフォルト: 3）
    
    Returns
    -------
    tuple
        (model, states) のタプル
    """
    print(f"\n[INFO] Fitting HMM model with {n_components} states...")
    
    model = GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=200,
        random_state=42,  # 再現性のため
    )
    
    model.fit(X_scaled)
    states = model.predict(X_scaled)
    
    print(f"[INFO] HMM fitting completed")
    print(f"  States: {len(set(states))} unique regimes")
    for i in range(n_components):
        count = (states == i).sum()
        pct = count / len(states) * 100
        print(f"    Regime {i}: {count} days ({pct:.1f}%)")
    
    return model, states


def compute_regime_stats(df: pd.DataFrame) -> dict:
    """
    レジーム別統計を計算
    
    Parameters
    ----------
    df : pd.DataFrame
        date, regime, alpha を含むDataFrame
    
    Returns
    -------
    dict
        レジーム別統計
    """
    stats = {}
    
    for regime in sorted(df['regime'].unique()):
        df_regime = df[df['regime'] == regime].copy()
        
        if len(df_regime) == 0:
            continue
        
        # 年率α平均
        annual_alpha_mean = df_regime['alpha'].mean() * 252
        
        # 年率αシャープ
        annual_alpha_std = df_regime['alpha'].std() * np.sqrt(252)
        annual_alpha_sharpe = annual_alpha_mean / annual_alpha_std if annual_alpha_std > 0 else np.nan
        
        # 平均ドローダウン（dd_252の平均）
        avg_dd_252 = df_regime['dd_252'].mean() if 'dd_252' in df_regime.columns else np.nan
        
        # 2018年のα
        df_2018 = df_regime[df_regime['date'].dt.year == 2018]
        if len(df_2018) > 0:
            alpha_2018 = df_2018['alpha'].sum()  # 年次累積α
        else:
            alpha_2018 = np.nan
        
        # 2022年のα
        df_2022 = df_regime[df_regime['date'].dt.year == 2022]
        if len(df_2022) > 0:
            alpha_2022 = df_2022['alpha'].sum()  # 年次累積α
        else:
            alpha_2022 = np.nan
        
        # 日数 / 期間比率
        total_days = len(df)
        regime_days = len(df_regime)
        days_ratio = regime_days / total_days if total_days > 0 else 0.0
        
        # 期間
        period_start = df_regime['date'].min()
        period_end = df_regime['date'].max()
        
        stats[str(regime)] = {
            "annual_alpha_mean": float(annual_alpha_mean) if not np.isnan(annual_alpha_mean) else None,
            "annual_alpha_sharpe": float(annual_alpha_sharpe) if not np.isnan(annual_alpha_sharpe) else None,
            "avg_dd_252": float(avg_dd_252) if not np.isnan(avg_dd_252) else None,
            "alpha_2018": float(alpha_2018) if not np.isnan(alpha_2018) else None,
            "alpha_2022": float(alpha_2022) if not np.isnan(alpha_2022) else None,
            "days": int(regime_days),
            "days_ratio": float(days_ratio),
            "period_start": period_start.strftime("%Y-%m-%d") if pd.notna(period_start) else None,
            "period_end": period_end.strftime("%Y-%m-%d") if pd.notna(period_end) else None,
        }
    
    return stats


def assign_regime_names(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """
    レジーム名を付与（年率αでソート）
    
    Parameters
    ----------
    df : pd.DataFrame
        regime 列を含むDataFrame
    stats : dict
        レジーム別統計
    
    Returns
    -------
    pd.DataFrame
        regime_name 列を追加したDataFrame
    """
    # 年率αでソート
    regime_alpha = {
        int(k): v.get("annual_alpha_mean", 0.0) or 0.0 
        for k, v in stats.items()
    }
    
    ranking = sorted(regime_alpha.items(), key=lambda x: x[1])
    mapping = {
        ranking[0][0]: "R_weak",
        ranking[1][0]: "R_normal",
        ranking[2][0]: "R_good",
    }
    
    df = df.copy()
    df['regime_name'] = df['regime'].map(mapping)
    
    print("\n[INFO] Regime naming:")
    for regime, name in sorted(mapping.items()):
        alpha_mean = regime_alpha[regime]
        print(f"  Regime {regime}: {name} (annual_alpha: {alpha_mean:+.2%})")
    
    return df


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== HMM レジームクラスタリング ===")
    print("=" * 80)
    
    # 1. 入力データを読み込む
    print("\n[STEP 1] Loading alpha series...")
    df = load_alpha_series()
    
    if df is None or df.empty:
        print("[ERROR] Failed to load alpha series")
        return
    
    print(f"  Data period: {df['date'].min().date()} ～ {df['date'].max().date()}")
    print(f"  Data points: {len(df)}")
    
    # 2. 特徴量を計算
    print("\n[STEP 2] Computing features...")
    df = compute_features(df)
    
    # 特徴量の基本統計
    features = ['alpha', 'roll_alpha_mean_63', 'roll_alpha_vol_63', 'dd_252']
    print(f"  Features: {', '.join(features)}")
    print(f"  Feature statistics:")
    for feat in features:
        if feat in df.columns:
            print(f"    {feat}: mean={df[feat].mean():.6f}, std={df[feat].std():.6f}")
    
    # 3. 標準化
    print("\n[STEP 3] Standardizing features...")
    X = df[features].dropna()
    
    if len(X) == 0:
        print("[ERROR] No valid features after dropna")
        return
    
    # 標準化（z-score）
    X_mean = X.mean()
    X_std = X.std()
    X_scaled = (X - X_mean) / X_std
    
    # NaNやInfをチェック
    if X_scaled.isnull().any().any() or np.isinf(X_scaled).any().any():
        print("[WARN] NaN or Inf found in scaled features. Filling with 0...")
        X_scaled = X_scaled.fillna(0).replace([np.inf, -np.inf], 0)
    
    print(f"  Scaled features shape: {X_scaled.shape}")
    print(f"  Valid data points: {len(X_scaled)}")
    
    # 4. HMMモデルを学習
    print("\n[STEP 4] Fitting HMM model...")
    model, states = fit_hmm(X_scaled.values, n_components=3)
    
    # 5. レジームラベルをDataFrameに追加
    df_result = df.copy()
    df_result['regime'] = np.nan
    
    # X_scaledのインデックスに合わせてレジームを割り当て
    valid_indices = X.index
    df_result.loc[valid_indices, 'regime'] = states
    
    # NaNはforward fill（最初のNaNは後方埋め）
    df_result['regime'] = df_result['regime'].ffill().bfill()
    df_result['regime'] = df_result['regime'].astype(int)
    
    # 必要な列のみを残す
    output_cols = ['date', 'regime', 'alpha', 'roll_alpha_mean_63', 'roll_alpha_vol_63', 'dd_252']
    df_result = df_result[output_cols].copy()
    
    # 6. レジーム別統計を計算
    print("\n[STEP 5] Computing regime statistics...")
    stats = compute_regime_stats(df_result)
    
    # 7. レジーム名を付与
    print("\n[STEP 6] Assigning regime names...")
    df_result = assign_regime_names(df_result, stats)
    
    # 8. 出力を保存
    print("\n[STEP 7] Saving results...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # regime_labels.parquet
    output_path = DATA_DIR / "regime_labels.parquet"
    df_result.to_parquet(output_path, index=False)
    print(f"[INFO] Saved regime labels to {output_path}")
    
    # regime_stats.json
    stats_path = DATA_DIR / "regime_stats.json"
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Saved regime statistics to {stats_path}")
    
    # 9. サマリーを表示
    print("\n" + "=" * 80)
    print("=== レジーム別統計サマリー ===")
    print("=" * 80)
    
    for regime, stat in sorted(stats.items()):
        print(f"\n【Regime {regime}】")
        print(f"  期間: {stat['period_start']} ～ {stat['period_end']}")
        print(f"  日数: {stat['days']} ({stat['days_ratio']:.2%})")
        print(f"  年率α平均: {stat['annual_alpha_mean']:+.4%}" if stat['annual_alpha_mean'] is not None else "  年率α平均: N/A")
        print(f"  年率αシャープ: {stat['annual_alpha_sharpe']:+.4f}" if stat['annual_alpha_sharpe'] is not None else "  年率αシャープ: N/A")
        print(f"  平均DD(252): {stat['avg_dd_252']:+.4%}" if stat['avg_dd_252'] is not None else "  平均DD(252): N/A")
        print(f"  2018年α: {stat['alpha_2018']:+.4%}" if stat['alpha_2018'] is not None else "  2018年α: N/A")
        print(f"  2022年α: {stat['alpha_2022']:+.4%}" if stat['alpha_2022'] is not None else "  2022年α: N/A")
    
    print("\n" + "=" * 80)
    print("=== 完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    main()

