#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/calc_minimum_capital.py

eval_stop_regimes.pyで計算されるポートフォリオと株価から
ポートフォリオ構築に必要な最小金額を計算するスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np

DATA_DIR = Path("data/processed")
RAW_DATA_DIR = Path("data/raw")


def load_inverse_etf_price() -> float:
    """
    1569.T（インバースETF）の最新価格を取得
    
    Returns
    -------
    float
        最新価格（円）
    """
    inverse_paths = [
        RAW_DATA_DIR / "equities" / "1569.T.parquet",
        DATA_DIR / "inverse_returns.parquet",
    ]
    
    for path in inverse_paths:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                
                # 日付カラムを確認
                date_col = None
                for col in ["date", "trade_date", "datetime"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col is None:
                    continue
                
                df[date_col] = pd.to_datetime(df[date_col])
                df = df.set_index(date_col).sort_index()
                
                # 価格カラムを確認
                price_col = None
                for col in ["close", "adj_close", "Close", "Adj Close"]:
                    if col in df.columns:
                        price_col = col
                        break
                
                if price_col is None:
                    continue
                
                latest_price = df[price_col].iloc[-1]
                print(f"[INFO] 1569.T 最新価格: {latest_price:.0f}円 (データソース: {path})")
                return float(latest_price)
                
            except Exception as e:
                print(f"[WARN] Failed to load from {path}: {e}")
                continue
    
    # デフォルト値（参考値）
    print("[WARN] 1569.Tの価格データが見つかりません。デフォルト値を使用します。")
    return 2000.0  # 参考値


def estimate_cross4_holdings() -> dict:
    """
    cross4ポートフォリオの推定保有銘柄数を返す
    
    Returns
    -------
    dict
        推定情報を含む辞書
    """
    # universe.ymlから推定
    # top_ratio: 0.20 で上位20%の銘柄を使用
    # 実際のユニバースサイズは変動するが、おおよその目安を提供
    
    # 参考: README.mdによると、ユニバースは流動性の高い銘柄から選択
    # 実際の運用では、各ホライゾンで異なる銘柄を保有する可能性がある
    
    # 保守的な推定値
    estimated_holdings = {
        "min_holdings": 20,  # 最低限の分散
        "typical_holdings": 30,  # 典型的な保有数
        "max_holdings": 50,  # 最大保有数
        "avg_price_per_stock": 3000.0,  # 1銘柄あたりの平均価格（円）
        "min_lot_size": 100,  # 最小売買単位（通常100株）
    }
    
    return estimated_holdings


def calculate_minimum_capital(
    strategy: str = "planA_60",
    inverse_price: float = None,
    holdings_info: dict = None,
) -> dict:
    """
    各戦略に必要な最小金額を計算
    
    Parameters
    ----------
    strategy : str
        戦略名 ("baseline", "stop0_60", "planA_60", "planB_60")
    inverse_price : float
        インバースETF（1569.T）の価格
    holdings_info : dict
        cross4の保有銘柄情報
    
    Returns
    -------
    dict
        最小金額と内訳を含む辞書
    """
    if inverse_price is None:
        inverse_price = load_inverse_etf_price()
    
    if holdings_info is None:
        holdings_info = estimate_cross4_holdings()
    
    # cross4の最小金額を計算
    # 各銘柄を最小売買単位（100株）で保有する場合
    min_stock_price = holdings_info["avg_price_per_stock"]
    min_lot_size = holdings_info["min_lot_size"]
    typical_holdings = holdings_info["typical_holdings"]
    
    # cross4の最小金額（全銘柄を最小単位で保有）
    cross4_min_capital = typical_holdings * min_stock_price * min_lot_size
    
    # 戦略別の最小金額
    results = {}
    
    # Baseline: cross4 100%
    results["baseline"] = {
        "strategy": "Baseline (cross4 100%)",
        "cross4_amount": cross4_min_capital,
        "inverse_amount": 0.0,
        "cash_amount": 0.0,
        "total_minimum": cross4_min_capital,
        "breakdown": {
            "cross4": f"{cross4_min_capital:,.0f}円",
            "inverse": "0円",
            "cash": "0円",
        }
    }
    
    # STOP0: STOP中は現金100%
    # 通常時はcross4 100%、STOP中は現金100%
    # 最大エクスポージャはcross4 100%なので、cross4の最小金額が必要
    results["stop0_60"] = {
        "strategy": "STOP0 60d (STOP中は現金100%)",
        "cross4_amount": cross4_min_capital,
        "inverse_amount": 0.0,
        "cash_amount": 0.0,  # 現金は追加資金不要
        "total_minimum": cross4_min_capital,
        "breakdown": {
            "cross4": f"{cross4_min_capital:,.0f}円",
            "inverse": "0円",
            "cash": "0円（既存資金で対応）",
        }
    }
    
    # Plan A: STOP中はcross4 75% + inverse 25%
    # 通常時: cross4 100%
    # STOP中: cross4 75% + inverse 25%
    # 
    # 実際の運用では、STOP期間中にcross4の25%分を売却してinverseを購入するため、
    # 追加資金は基本的に不要です。
    # ただし、リバランス時の流動性と価格変動を考慮して、余裕を持たせる必要があります。
    
    # cross4 100%分の資金（基本資金）
    cross4_base = cross4_min_capital
    
    # inverse 25%分の資金（cross4の25%相当）
    # STOP期間中にcross4の25%を売却してinverseを購入するため、
    # 理論上は追加資金は不要ですが、リバランス時の流動性を考慮
    inverse_25pct = cross4_min_capital * 0.25
    
    # inverse ETFの最小購入単位（1口）
    inverse_min_lot = 1
    
    # inverse 25%を満たすために必要な口数
    inverse_shares_needed = max(1, int(np.ceil(inverse_25pct / inverse_price)))
    inverse_actual_amount = inverse_shares_needed * inverse_price
    
    # 総額: cross4 100%分の資金があれば、リバランスで対応可能
    # ただし、リバランス時の流動性リスクを考慮して、inverse分の資金も用意しておく方が安全
    # 保守的な見積もり: cross4 100% + inverse 25%相当
    # 現実的な見積もり: cross4 100%のみ（リバランスで対応）
    planA_total_conservative = cross4_base + inverse_actual_amount
    planA_total_realistic = cross4_base
    
    results["planA_60"] = {
        "strategy": "Plan A 60d (STOP中: cross4 75% + inverse 25%)",
        "cross4_amount": cross4_base,
        "inverse_amount": inverse_actual_amount,
        "cash_amount": 0.0,
        "total_minimum": planA_total_realistic,  # 現実的な見積もり
        "total_minimum_conservative": planA_total_conservative,  # 保守的な見積もり
        "breakdown": {
            "cross4": f"{cross4_base:,.0f}円（100%エクスポージャ）",
            "inverse": f"{inverse_actual_amount:,.0f}円（{inverse_shares_needed}口、cross4の25%相当、リバランスで対応）",
            "cash": "0円",
        },
        "notes": "通常時はcross4 100%、STOP中はcross4 75% + inverse 25%。リバランスでcross4の25%を売却してinverseを購入するため、追加資金は基本的に不要。保守的な見積もり: {planA_total_conservative:,.0f}円".format(planA_total_conservative=planA_total_conservative)
    }
    
    # Plan B: STOP中はcross4 50% + cash 50%
    # 通常時: cross4 100%
    # STOP中: cross4 50% + cash 50%
    # 最大エクスポージャはcross4 100%なので、cross4の最小金額が必要
    # 現金は追加資金不要（既存のcross4ポジションを50%現金化）
    results["planB_60"] = {
        "strategy": "Plan B 60d (STOP中: cross4 50% + cash 50%)",
        "cross4_amount": cross4_min_capital,
        "inverse_amount": 0.0,
        "cash_amount": 0.0,  # 現金は追加資金不要
        "total_minimum": cross4_min_capital,
        "breakdown": {
            "cross4": f"{cross4_min_capital:,.0f}円（100%エクスポージャ）",
            "inverse": "0円",
            "cash": "0円（既存資金で対応）",
        },
        "notes": "通常時はcross4 100%、STOP中はcross4 50% + cash 50%"
    }
    
    return results


def print_minimum_capital_report(results: dict, inverse_price: float, holdings_info: dict):
    """
    最小金額レポートを表示
    
    Parameters
    ----------
    results : dict
        calculate_minimum_capital()の結果
    inverse_price : float
        インバースETFの価格
    holdings_info : dict
        保有銘柄情報
    """
    print("=" * 80)
    print("=== ポートフォリオ構築に必要な最小金額 ===")
    print("=" * 80)
    
    print("\n【前提条件】")
    print(f"  1569.T（インバースETF）価格: {inverse_price:,.0f}円")
    print(f"  cross4推定保有銘柄数: {holdings_info['typical_holdings']}銘柄")
    print(f"  1銘柄あたり平均価格: {holdings_info['avg_price_per_stock']:,.0f}円")
    print(f"  最小売買単位: {holdings_info['min_lot_size']}株")
    print(f"  cross4最小金額（推定）: {holdings_info['typical_holdings'] * holdings_info['avg_price_per_stock'] * holdings_info['min_lot_size']:,.0f}円")
    
    print("\n【各戦略の最小金額】")
    print("-" * 80)
    
    for strategy_key, result in results.items():
        print(f"\n{result['strategy']}")
        if 'total_minimum_conservative' in result:
            print(f"  最小金額（現実的）: {result['total_minimum']:,.0f}円")
            print(f"  最小金額（保守的）: {result['total_minimum_conservative']:,.0f}円")
        else:
            print(f"  最小金額: {result['total_minimum']:,.0f}円")
        print("  内訳:")
        for asset, amount in result['breakdown'].items():
            print(f"    {asset}: {amount}")
        if 'notes' in result:
            print(f"  備考: {result['notes']}")
    
    print("\n" + "=" * 80)
    print("【注意事項】")
    print("1. 上記は最小金額の目安です。実際の運用では以下を考慮してください:")
    print("   - 手数料・スプレッド")
    print("   - リバランス時の追加資金")
    print("   - 価格変動による追加マージン")
    print("   - 流動性リスク")
    print("2. cross4の実際の保有銘柄数は変動します。")
    print("3. 最小売買単位は銘柄によって異なります（100株、1,000株など）。")
    print("4. Plan Aでは、STOP期間中にcross4とinverseを同時に保有するため、")
    print("   両方の資金が必要です。")
    print("=" * 80)


def main():
    """メイン処理"""
    print("=" * 80)
    print("=== ポートフォリオ最小金額計算 ===")
    print("=" * 80)
    
    # 1. インバースETF価格を取得
    print("\n[STEP 1] Loading inverse ETF price...")
    inverse_price = load_inverse_etf_price()
    
    # 2. cross4の保有銘柄情報を推定
    print("\n[STEP 2] Estimating cross4 holdings...")
    holdings_info = estimate_cross4_holdings()
    print(f"  推定保有銘柄数: {holdings_info['typical_holdings']}銘柄")
    print(f"  1銘柄あたり平均価格: {holdings_info['avg_price_per_stock']:,.0f}円")
    
    # 3. 各戦略の最小金額を計算
    print("\n[STEP 3] Calculating minimum capital for each strategy...")
    results = calculate_minimum_capital(
        strategy="planA_60",
        inverse_price=inverse_price,
        holdings_info=holdings_info,
    )
    
    # 4. レポートを表示
    print_minimum_capital_report(results, inverse_price, holdings_info)
    
    # 5. 結果を保存
    output_path = DATA_DIR / "minimum_capital_report.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("=== ポートフォリオ構築に必要な最小金額 ===\n")
        f.write("=" * 80 + "\n\n")
        
        for strategy_key, result in results.items():
            f.write(f"{result['strategy']}\n")
            f.write(f"  最小金額: {result['total_minimum']:,.0f}円\n")
            f.write("  内訳:\n")
            for asset, amount in result['breakdown'].items():
                f.write(f"    {asset}: {amount}\n")
            if 'notes' in result:
                f.write(f"  備考: {result['notes']}\n")
            f.write("\n")
    
    print(f"\n[INFO] レポートを保存しました: {output_path}")


if __name__ == "__main__":
    main()

