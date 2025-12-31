"""
run_dryrun.py

execution dry-runの実行入口。

core成果物（daily_portfolio_guarded.parquet）の最新日を読み、
前日スナップショットと比較してorder_intentを生成・出力する。
"""
from pathlib import Path
import sys

import pandas as pd

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.read_latest import read_latest_portfolio
from execution.state_store import StateStore
from execution.build_order_intent import build_order_intent
from execution.write_order_intent import OrderIntentWriter
from tools.lib import data_loader


def main():
    """dry-run実行"""
    print("=" * 80)
    print("execution dry-run: order_intent生成")
    print("=" * 80)
    
    # 0. latest_date進行ガード（run_guard）
    print("\n[0] latest_date進行チェック中...")
    store = StateStore()
    df_latest = read_latest_portfolio()
    latest_date = df_latest["date"].iloc[0]
    latest_date_normalized = pd.to_datetime(latest_date).normalize()
    
    last_executed_date = store.get_last_executed_latest_date()
    
    if last_executed_date is not None:
        last_executed_date_normalized = pd.to_datetime(last_executed_date).normalize()
        
        if latest_date_normalized == last_executed_date_normalized:
            # latest_dateが進んでいない（祝日などでデータ更新なし）
            print(f"SKIP: latest_dateが進んでいません（{latest_date_normalized.date()}）")
            print("前回実行時のlatest_dateと同じため、order_intent生成をスキップします。")
            
            # SKIPログを出力
            writer = OrderIntentWriter()
            reason = f"latest_date unchanged: {latest_date_normalized.date()}"
            writer.write_skip(latest_date_normalized, reason)
            
            print("=" * 80)
            return
    
    print(f"最新日: {latest_date_normalized.date()}")
    if last_executed_date is not None:
        print(f"前回実行時のlatest_date: {last_executed_date_normalized.date()}")
        print(f"データ進行: {last_executed_date_normalized.date()} → {latest_date_normalized.date()}")
    else:
        print("前回実行履歴なし（初回実行）")
    
    # 1. 最新ポートフォリオを読み込む（既に読み込み済み）
    print("\n[1] 最新ポートフォリオ確認...")
    print(f"銘柄数: {len(df_latest)}")
    
    # 2. 前日状態を読み込む
    print("\n[2] 前日状態を読み込み中...")
    prev_weights = store.get_prev_weights()
    if prev_weights is not None:
        print(f"前日銘柄数: {len(prev_weights)}")
    else:
        print("前日状態なし（初回実行）")
    
    # 3. 価格データを読み込む（order_intent計算に必要）
    print("\n[3] 価格データを読み込み中...")
    prices_df = data_loader.load_prices()
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    
    # 最新日の価格を取得
    latest_prices_df = prices_df[prices_df["date"] == latest_date]
    if latest_prices_df.empty:
        # 最新日が無い場合は最新の有効な日を取得
        latest_prices_df = prices_df[prices_df["date"] <= latest_date].sort_values("date").groupby("symbol").last().reset_index()
    
    if "symbol" in latest_prices_df.columns and "close" in latest_prices_df.columns:
        prices_series = latest_prices_df.set_index("symbol")["close"]
    else:
        # フォールバック: 価格が取得できない場合は0を設定（警告を出す）
        print("警告: 価格データが取得できません。価格を0として処理します。")
        prices_series = pd.Series(0.0, index=df_latest["symbol"].unique())
    
    # 4. order_intentを計算
    print("\n[4] order_intentを計算中...")
    target_weights = df_latest.set_index("symbol")["weight"]
    df_intent = build_order_intent(
        target_weights=target_weights,
        prev_weights=prev_weights,
        prices=prices_series,
        latest_date=latest_date_normalized,
    )
    
    print(f"order_intent銘柄数: {len(df_intent)}")
    print(f"合計delta_weight: {df_intent['delta_weight'].sum():.4f}")
    
    # 5. order_intentを出力
    print("\n[5] order_intentを出力中...")
    writer = OrderIntentWriter()
    writer.write(df_intent, latest_date, format="both")
    
    # 6. 現在の状態を保存（次回実行時の前日状態として）
    print("\n[6] 現在の状態を保存中...")
    store.save_state(df_latest, latest_date)
    
    # 7. latest_date進行ガードを更新（run_guard）
    print("\n[7] latest_date進行ガードを更新中...")
    store.save_last_executed_latest_date(latest_date_normalized)
    
    print("\n" + "=" * 80)
    print("dry-run完了")
    print("=" * 80)
    print(f"\norder_intentの先頭10行:")
    display_cols = ["latest_date", "symbol", "prev_weight", "target_weight", "delta_weight", "notional_delta", "notes"]
    display_cols = [c for c in display_cols if c in df_intent.columns]
    print(df_intent[display_cols].head(10))


if __name__ == "__main__":
    main()
