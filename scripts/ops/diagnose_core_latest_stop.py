#!/usr/bin/env python
"""
診断スクリプト: core の latest が止まった原因を特定する

入力:
- data/processed/daily_feature_scores.parquet
- data/processed/daily_portfolio_guarded.parquet
- (可能なら) universe parquet

出力:
- 日付別の行数（feature / portfolio）
- 12/29 の symbol 一覧（featureに残った銘柄、落ちた銘柄の推定）
- 欠損列チェック（feature計算に必須な列の欠損）
- 12/29 の build_features ログからエラーを抽出（ログファイルがある場合）
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

def check_feature_scores():
    """feature_scoresの診断"""
    path = Path("data/processed/daily_feature_scores.parquet")
    if not path.exists():
        print(f"[ERROR] {path} が見つかりません")
        return None
    
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    
    print("=" * 60)
    print("=== feature_scores 診断 ===")
    print("=" * 60)
    
    # 日付別の行数
    print("\n【日付別の行数】")
    recent_dates = pd.date_range(end=df["date"].max(), periods=5, freq="D")
    for d in recent_dates:
        if d <= df["date"].max():
            cnt = len(df[df["date"] == d])
            print(f"  {d.strftime('%Y-%m-%d')}: {cnt}行")
    
    # 最新日の詳細
    latest_date = df["date"].max()
    latest_df = df[df["date"] == latest_date].copy()
    
    print(f"\n【最新日: {latest_date.strftime('%Y-%m-%d')}】")
    print(f"  行数: {len(latest_df)}")
    
    if len(latest_df) > 0:
        print(f"  銘柄数: {latest_df['symbol'].nunique()}")
        print(f"  銘柄一覧: {sorted(latest_df['symbol'].unique().tolist())}")
        
        # NaT/NaNチェック
        print("\n【欠損値チェック】")
        for col in ["date", "symbol", "close", "adj_close", "feature_score", "adv_20d"]:
            if col in latest_df.columns:
                na_count = latest_df[col].isna().sum()
                nat_count = (pd.isna(latest_df[col]) & (latest_df[col] != latest_df[col])).sum() if col == "date" else 0
                if na_count > 0 or nat_count > 0:
                    print(f"  {col}: NaN={na_count}, NaT={nat_count}")
        
        # 必須列の存在確認
        required_cols = ["date", "symbol", "close", "adj_close", "feature_score", "adv_20d"]
        missing_cols = [c for c in required_cols if c not in latest_df.columns]
        if missing_cols:
            print(f"\n  [WARNING] 必須列が欠損: {missing_cols}")
    
    # 12/29の詳細（特に重要）
    target_date = pd.to_datetime("2025-12-29")
    if target_date <= df["date"].max():
        target_df = df[df["date"] == target_date].copy()
        print(f"\n【12/29 の詳細】")
        print(f"  行数: {len(target_df)}")
        
        if len(target_df) > 0:
            print(f"  銘柄: {target_df['symbol'].tolist()}")
            
            # 各列の欠損状況
            print("\n  列別の欠損状況:")
            for col in target_df.columns:
                na_count = target_df[col].isna().sum()
                if na_count > 0:
                    print(f"    {col}: {na_count}/{len(target_df)} がNaN")
            
            # 12/26との比較（正常な日）
            normal_date = pd.to_datetime("2025-12-26")
            if normal_date <= df["date"].max():
                normal_df = df[df["date"] == normal_date].copy()
                normal_symbols = set(normal_df["symbol"].unique())
                target_symbols = set(target_df["symbol"].unique())
                
                print(f"\n  12/26との比較:")
                print(f"    12/26の銘柄数: {len(normal_symbols)}")
                print(f"    12/29の銘柄数: {len(target_symbols)}")
                print(f"    12/29に存在する銘柄: {sorted(target_symbols)}")
                print(f"    12/29に欠落した銘柄: {sorted(normal_symbols - target_symbols)}")
    
    return df

def check_portfolio():
    """portfolioの診断"""
    path = Path("data/processed/daily_portfolio_guarded.parquet")
    if not path.exists():
        print(f"[ERROR] {path} が見つかりません")
        return None
    
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    
    print("\n" + "=" * 60)
    print("=== portfolio 診断 ===")
    print("=" * 60)
    
    # 日付別の行数
    print("\n【日付別の行数】")
    recent_dates = pd.date_range(end=df["date"].max(), periods=5, freq="D")
    for d in recent_dates:
        if d <= df["date"].max():
            cnt = len(df[df["date"] == d])
            print(f"  {d.strftime('%Y-%m-%d')}: {cnt}行")
    
    latest_date = df["date"].max()
    print(f"\n【最新日: {latest_date.strftime('%Y-%m-%d')}】")
    print(f"  行数: {len(df[df['date'] == latest_date])}")
    
    return df

def check_logs():
    """build_features.pyのログからエラーを抽出"""
    print("\n" + "=" * 60)
    print("=== ログ診断 ===")
    print("=" * 60)
    
    log_dir = Path("logs")
    if not log_dir.exists():
        print("[WARNING] logs ディレクトリが見つかりません")
        return
    
    # 12/29のログを探す
    log_files = sorted(log_dir.glob("run_equity01_core_*.log"), reverse=True)
    
    target_date_str = "20251229"
    target_log = None
    for log_file in log_files:
        if target_date_str in log_file.name:
            target_log = log_file
            break
    
    if target_log is None:
        print(f"[WARNING] {target_date_str} のログが見つかりません")
        return
    
    print(f"\n【ログファイル: {target_log.name}】")
    
    with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    # build_features.py関連の行を抽出
    in_build_features = False
    build_features_lines = []
    errors = []
    
    for i, line in enumerate(lines):
        if "build_features.py" in line:
            in_build_features = True
            build_features_lines = []
        elif in_build_features:
            build_features_lines.append((i, line))
            if "build_portfolio.py" in line or "START:" in line and "build_features" not in line:
                in_build_features = False
            if "ERROR" in line.upper() or "Exception" in line or "Traceback" in line:
                errors.append((i, line))
    
    if build_features_lines:
        print(f"\n  build_features.py セクション: {len(build_features_lines)}行")
        
        # エラー行を表示
        if errors:
            print("\n  【エラー/例外】")
            for i, line in errors[:10]:  # 最大10行
                print(f"    L{i}: {line.strip()}")
        else:
            print("  [INFO] エラー/例外は見つかりませんでした")
        
        # 重要なキーワードを検索
        keywords = ["symbols:", "NaT", "NaN", "dropna", "merge", "join"]
        found_keywords = []
        for i, line in build_features_lines:
            for kw in keywords:
                if kw in line:
                    found_keywords.append((i, kw, line.strip()[:100]))
        
        if found_keywords:
            print("\n  【重要なキーワード】")
            for i, kw, snippet in found_keywords[:10]:
                print(f"    L{i} [{kw}]: {snippet}")

def main():
    print("=" * 60)
    print("core latest停止 診断レポート")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    df_feat = check_feature_scores()
    df_port = check_portfolio()
    check_logs()
    
    print("\n" + "=" * 60)
    print("診断完了")
    print("=" * 60)

if __name__ == "__main__":
    main()

