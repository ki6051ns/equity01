"""
各ホライゾンのバックテスト進捗を確認するスクリプト
"""
import pandas as pd
from pathlib import Path

horizons = [1, 5, 10, 20, 60]

print("=" * 60)
print("=== ホライゾン別バックテスト進捗確認 ===")
print("=" * 60)

for h in horizons:
    pt_path = Path(f"data/processed/paper_trade_h{h}.parquet")
    alpha_path = Path(f"data/processed/paper_trade_with_alpha_beta_h{h}.parquet")
    
    print(f"\nH{h}:")
    if pt_path.exists():
        df_pt = pd.read_parquet(pt_path)
        print(f"  paper_trade_h{h}.parquet: {len(df_pt)} 日分")
        
        # port_ret_ccが全て0かチェック
        if "port_ret_cc" in df_pt.columns:
            zero_count = (df_pt["port_ret_cc"] == 0).sum()
            non_zero_count = (df_pt["port_ret_cc"] != 0).sum()
            print(f"    port_ret_cc: ゼロ={zero_count}, 非ゼロ={non_zero_count}")
            if non_zero_count > 0:
                print(f"    port_ret_cc stats: mean={df_pt['port_ret_cc'].mean():.6f}, std={df_pt['port_ret_cc'].std():.6f}")
        else:
            print(f"    port_ret_cc列がありません")
    else:
        print(f"  paper_trade_h{h}.parquet: 存在しません")
    
    if alpha_path.exists():
        df_alpha = pd.read_parquet(alpha_path)
        print(f"  paper_trade_with_alpha_beta_h{h}.parquet: {len(df_alpha)} 日分")
        
        if "port_ret_cc" in df_alpha.columns:
            total_port = (1 + df_alpha["port_ret_cc"]).prod() - 1
            print(f"    累積Port: {total_port:+.4%}")
    else:
        print(f"  paper_trade_with_alpha_beta_h{h}.parquet: 存在しません")

print("\n" + "=" * 60)

