"""
ホライゾン別・Variant別の年次パフォーマンスを集計するスクリプト

2018年と2022年のデータを抽出して表にまとめる
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DATA_DIR = Path("data/processed")

# Variant とホライゾンの定義
VARIANTS = {
    "zlin": "z_lin (Variant A)",
    "rank": "rank_only (Variant B)",
    "zclip": "z_clip_rank (Variant C)",
    "zlowvol": "z_lowvol (Variant D)",
    "zdownvol": "z_downvol (Variant E)",
    "zdownbeta": "z_downbeta (Variant F)",
    "zdowncombo": "z_downcombo (Variant G)",
}

HORIZONS = [1, 5, 10, 60, 90, 120]
TARGET_YEARS = [2018, 2022]

def load_yearly_data(variant: str, horizon: int) -> pd.DataFrame:
    """
    年次パフォーマンスデータを読み込む
    
    Parameters
    ----------
    variant : str
        バリアント名（zlin, rank, zclip, zlowvol, zdownvol, zdownbeta, zdowncombo）
    horizon : int
        ホライゾン（1, 5, 10, 60, 90, 120）
    
    Returns
    -------
    pd.DataFrame
        年次パフォーマンスデータ（year, port_return, tpx_return, rel_alpha, days）
    """
    # ファイル名のパターンを試す（compute_monthly_perf の label パターンに合わせる）
    # label は "zclip_h1", "zlin_h5", "rank_only_h10" などの形式
    patterns = [
        f"horizon_yearly_{variant}_h{horizon}.parquet",  # 標準パターン
        f"horizon_yearly_{variant}_H{horizon}.parquet",  # 大文字H
    ]
    
    # rank_only の場合は特別なパターン
    if variant == "rank":
        patterns.insert(0, f"horizon_yearly_rank_only_h{horizon}.parquet")
    
    for pattern in patterns:
        file_path = DATA_DIR / pattern
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                return df
            except Exception as e:
                print(f"  警告: {file_path} の読み込みに失敗: {e}")
                continue
    
    return pd.DataFrame()


def aggregate_yearly_performance():
    """
    ホライゾン別・Variant別の年次パフォーマンスを集計
    """
    print("=" * 80)
    print("=== ホライゾン別・Variant別 年次パフォーマンス集計 ===")
    print("=" * 80)
    print(f"対象年: {TARGET_YEARS}")
    print()
    
    # まず、存在するファイルを確認
    print("[STEP 1] 年次パフォーマンスファイルを検索中...")
    all_files = list(DATA_DIR.glob("horizon_yearly_*.parquet"))
    print(f"  見つかったファイル数: {len(all_files)}")
    
    if len(all_files) == 0:
        print("⚠️  horizon_yearly_*.parquet ファイルが見つかりません。")
        print("  先に run_all_*.py スクリプトを実行して年次データを生成してください。")
        return
    
    # データを収集
    all_data = []
    
    print("\n[STEP 2] データを読み込み中...")
    loaded_count = 0
    for variant_key, variant_name in VARIANTS.items():
        for horizon in HORIZONS:
            df = load_yearly_data(variant_key, horizon)
            
            if df.empty:
                continue
            
            loaded_count += 1
            print(f"  ✓ {variant_key} H{horizon}: {len(df)} 年分")
            
            # 対象年のデータを抽出
            for year in TARGET_YEARS:
                year_data = df[df["year"] == year]
                
                if len(year_data) == 0:
                    continue
                
                row = year_data.iloc[0]
                all_data.append({
                    "variant": variant_name,
                    "variant_key": variant_key,
                    "horizon": horizon,
                    "year": year,
                    "port_return": row.get("port_return", np.nan),
                    "tpx_return": row.get("tpx_return", np.nan),
                    "rel_alpha": row.get("rel_alpha", np.nan),
                    "days": row.get("days", np.nan),
                })
    
    print(f"\n  読み込み完了: {loaded_count} ファイル")
    
    if not all_data:
        print("⚠️  データが見つかりませんでした。")
        print("\n存在するファイルの例:")
        sample_files = list(DATA_DIR.glob("horizon_yearly_*.parquet"))[:5]
        for f in sample_files:
            print(f"  - {f.name}")
        return
    
    df_all = pd.DataFrame(all_data)
    print(f"\n[STEP 3] 集計データ: {len(df_all)} 行")
    
    # 2018年と2022年で別々の表を作成
    for year in TARGET_YEARS:
        print(f"\n{'=' * 80}")
        print(f"=== {year}年 パフォーマンス ===")
        print(f"{'=' * 80}")
        
        df_year = df_all[df_all["year"] == year].copy()
        
        if df_year.empty:
            print(f"  {year}年のデータが見つかりませんでした。")
            continue
        
        # ピボットテーブルを作成（Variant × Horizon）
        pivot_port = df_year.pivot_table(
            index="variant",
            columns="horizon",
            values="port_return",
            aggfunc="first"
        )
        pivot_alpha = df_year.pivot_table(
            index="variant",
            columns="horizon",
            values="rel_alpha",
            aggfunc="first"
        )
        pivot_tpx = df_year.pivot_table(
            index="variant",
            columns="horizon",
            values="tpx_return",
            aggfunc="first"
        )
        
        # ポートフォリオリターン表
        print(f"\n【{year}年】ポートフォリオリターン (%)")
        print("-" * 80)
        if not pivot_port.empty:
            display_port = pivot_port.copy()
            display_port = display_port.applymap(lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A")
            print(display_port.to_string())
        else:
            print("  データなし")
        
        # 相対α表
        print(f"\n【{year}年】相対α (%)")
        print("-" * 80)
        if not pivot_alpha.empty:
            display_alpha = pivot_alpha.copy()
            display_alpha = display_alpha.applymap(lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A")
            print(display_alpha.to_string())
        else:
            print("  データなし")
        
        # TOPIXリターン表（参考）
        print(f"\n【{year}年】TOPIXリターン (%)")
        print("-" * 80)
        if not pivot_tpx.empty:
            display_tpx = pivot_tpx.copy()
            display_tpx = display_tpx.applymap(lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A")
            print(display_tpx.to_string())
        else:
            print("  データなし")
    
    # 比較表（2018年 vs 2022年）
    print(f"\n{'=' * 80}")
    print("=== 2018年 vs 2022年 比較 ===")
    print(f"{'=' * 80}")
    
    # Variant × Horizon ごとに比較
    comparison_data = []
    for variant_key, variant_name in VARIANTS.items():
        for horizon in HORIZONS:
            df_variant_h = df_all[
                (df_all["variant_key"] == variant_key) & 
                (df_all["horizon"] == horizon)
            ]
            
            if df_variant_h.empty:
                continue
            
            row_2018 = df_variant_h[df_variant_h["year"] == 2018]
            row_2022 = df_variant_h[df_variant_h["year"] == 2022]
            
            comparison_data.append({
                "variant": variant_name,
                "horizon": horizon,
                "port_2018": row_2018["port_return"].iloc[0] if len(row_2018) > 0 else np.nan,
                "alpha_2018": row_2018["rel_alpha"].iloc[0] if len(row_2018) > 0 else np.nan,
                "port_2022": row_2022["port_return"].iloc[0] if len(row_2022) > 0 else np.nan,
                "alpha_2022": row_2022["rel_alpha"].iloc[0] if len(row_2022) > 0 else np.nan,
            })
    
    if comparison_data:
        df_comp = pd.DataFrame(comparison_data)
        
        print("\n【ポートフォリオリターン比較】")
        print("-" * 80)
        display_comp_port = df_comp[["variant", "horizon", "port_2018", "port_2022"]].copy()
        display_comp_port["port_2018"] = display_comp_port["port_2018"].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A"
        )
        display_comp_port["port_2022"] = display_comp_port["port_2022"].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A"
        )
        print(display_comp_port.to_string(index=False))
        
        print("\n【相対α比較】")
        print("-" * 80)
        display_comp_alpha = df_comp[["variant", "horizon", "alpha_2018", "alpha_2022"]].copy()
        display_comp_alpha["alpha_2018"] = display_comp_alpha["alpha_2018"].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A"
        )
        display_comp_alpha["alpha_2022"] = display_comp_alpha["alpha_2022"].apply(
            lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A"
        )
        print(display_comp_alpha.to_string(index=False))
    
    # CSV出力（オプション）
    output_path = DATA_DIR / "yearly_performance_summary_2018_2022.csv"
    df_all.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n✓ 詳細データをCSVに保存: {output_path}")
    
    print("\n" + "=" * 80)
    print("=== 集計完了 ===")
    print("=" * 80)


if __name__ == "__main__":
    aggregate_yearly_performance()
