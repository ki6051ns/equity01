"""
全ホライゾンでz_clip_rank (Variant C) バックテストを実行するスクリプト

H1/H5/H10: 非ラダー方式
H60/H90/H120: ラダー方式
"""
import sys
from pathlib import Path
import pandas as pd

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from horizon_ensemble import (
    build_features_shared,
    backtest_with_horizon,
    calc_alpha_beta_for_horizon,
    summarize_horizon,
    compute_monthly_perf,
    print_horizon_performance,
)
from backtest_non_ladder import backtest_non_ladder
import backtest_non_ladder as backtest_non_ladder_module

# BACKTEST_MODE を "z_clip_rank" に設定
import horizon_ensemble

horizon_ensemble.BACKTEST_MODE = "z_clip_rank"
backtest_non_ladder_module.BACKTEST_MODE = "z_clip_rank"

print("=" * 80)
print("=== 全ホライゾン z_clip_rank (Variant C) バックテスト実行 ===")
print("=" * 80)
print(f"BACKTEST_MODE: z_clip_rank")
print()

# アンサンブル設定（指定ウェイト）
ENSEMBLE_CONFIG = {
    1: {"weight": 0.10, "ladder": False},
    5: {"weight": 0.10, "ladder": False},
    10: {"weight": 0.20, "ladder": False},
    60: {"weight": 0.20, "ladder": True},
    90: {"weight": 0.20, "ladder": True},
    120: {"weight": 0.20, "ladder": True},
}

print("対象ホライゾン:")
for h in sorted(ENSEMBLE_CONFIG.keys()):
    cfg = ENSEMBLE_CONFIG[h]
    mode = "ラダー" if cfg["ladder"] else "非ラダー"
    print(f"  H{h}: {mode}")

# 共有featureと価格データを読み込み
print("\n[STEP 1] 共有featureと価格データを読み込み中...")
features, prices = build_features_shared()
print(f"  Features: {len(features)} rows")
print(f"  Prices: {len(prices)} rows")

# 必要なスコアカラムが存在するかチェック
required_col = "score_z_clip_rank"
if required_col not in features.columns:
    print(f"\n⚠️  警告: {required_col} カラムが見つかりません。")
    print(f"  先に build_features.py を実行して、Variant C のスコアを生成してください。")
    print(f"  現在のカラム: {features.columns.tolist()}")
    raise KeyError(f"Required column {required_col} not found. Please run build_features.py first.")

# 各ホライゾンのバックテストを実行
horizon_results = {}
summary_rows = []

for h, cfg in sorted(ENSEMBLE_CONFIG.items()):
    weight = cfg["weight"]
    is_ladder = cfg["ladder"]
    
    print(f"\n[STEP 2-{h}] H{h} z_clip_rank バックテスト実行中... ({'ラダー' if is_ladder else '非ラダー'})")
    
    # 既存ファイルを確認
    suffix_mode = "zclip"
    if is_ladder:
        pt_path = Path(f"data/processed/paper_trade_h{h}_ladder_{suffix_mode}.parquet")
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}_ladder_{suffix_mode}.parquet")
    else:
        pt_path = Path(f"data/processed/paper_trade_h{h}_nonladder_{suffix_mode}.parquet")
        alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}_nonladder_{suffix_mode}.parquet")
    
    # 既存ファイルがあれば読み込む、なければ実行
    # ただし、既存ファイルが空（0日分）の場合は再実行
    need_rerun = False
    if alpha_path.exists():
        print(f"  [H{h}] 既存ファイルを読み込み中...")
        df_alpha = pd.read_parquet(alpha_path)
        if len(df_alpha) == 0:
            print(f"  [H{h}] 既存ファイルが空のため、バックテストを再実行します")
            # 空のファイルを削除して再実行
            alpha_path.unlink(missing_ok=True)
            if pt_path.exists():
                pt_path.unlink(missing_ok=True)
            need_rerun = True
        else:
            print(f"  [H{h}] 既存ファイル読み込み完了: {len(df_alpha)} 日分")
    else:
        need_rerun = True
    
    # 既存ファイルが存在しない、または空だった場合はバックテストを実行
    if need_rerun:
        print(f"  [H{h}] バックテスト実行中...")
        if is_ladder:
            df_pt = backtest_with_horizon(features, prices, h)
        else:
            df_pt = backtest_non_ladder(features, prices, h)
        
        pt_path.parent.mkdir(parents=True, exist_ok=True)
        df_pt.to_parquet(pt_path, index=False)
        print(f"  [H{h}] バックテスト完了: {len(df_pt)} 日分")
        
        # 相対α計算
        print(f"  [H{h}] 相対α計算中...")
        df_alpha = calc_alpha_beta_for_horizon(df_pt, h)
        # ファイル名を上書き（calc_alpha_beta_for_horizon はラダー版のファイル名を生成するので）
        if not is_ladder:
            # 非ラダー版の場合はファイル名を修正
            alpha_path.parent.mkdir(parents=True, exist_ok=True)
            df_alpha.to_parquet(alpha_path, index=False)
        print(f"  [H{h}] 相対α計算完了")
    
    # サマリ計算
    summary = summarize_horizon(df_alpha, h)
    summary_rows.append({
        **summary,
        "weight": weight,
        "ladder": is_ladder,
    })
    
    print(
        f"  [H{h}] total_port={summary['total_port']:.2%}, "
        f"total_alpha={summary['total_alpha']:.2%}, "
        f"αSharpe={summary['alpha_sharpe_annual']:.2f}, "
        f"max_dd={summary['max_drawdown']:.2%}, "
        f"weight={weight:.2%}"
    )
    
    # 月次・年次パフォーマンスを計算・表示
    print(f"  [H{h}] 月次・年次集計中...")
    monthly, yearly = compute_monthly_perf(
        df_alpha,
        label=f"zclip_h{h}",
        out_prefix="data/processed/horizon"
    )
    print(f"  [H{h}] 月次・年次集計完了")
    
    # パフォーマンス表示
    print_horizon_performance(df_alpha, h, monthly, yearly)
    
    horizon_results[h] = df_alpha

# サマリテーブル表示
if summary_rows:
    import pandas as pd
    df_summary = pd.DataFrame(summary_rows)
    print("\n=== ホライゾン別パフォーマンスサマリ (z_clip_rank) ===")
    display_cols = ["horizon", "ladder", "weight", "days", "total_port", "total_tpx", "total_alpha", 
                   "alpha_sharpe_annual", "max_drawdown"]
    display_df = df_summary[display_cols].copy()
    for col in ["total_port", "total_tpx", "total_alpha", "max_drawdown", "weight"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:+.2%}")
    display_df["ladder"] = display_df["ladder"].apply(lambda x: "ラダー" if x else "非ラダー")
    print(display_df.to_string(index=False))

print("\n" + "=" * 80)
print("=== 全ホライゾン z_clip_rank バックテスト完了 ===")
print("=" * 80)
