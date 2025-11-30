"""
注文生成ヘルパー（Event Guard 統合用）

Event Guard のヘッジ注文を生成するためのユーティリティ関数。
実際の口座仕様に合わせて実装を調整してください。
"""
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional


@dataclass
class Order:
    """注文オブジェクト（簡易版）"""
    symbol: str
    side: str  # "BUY" or "SELL"
    qty: int
    order_type: str  # "MOC", "LIMIT", etc.
    comment: Optional[str] = None


def build_inverse_orders(
    inverse_symbol: str,
    hedge_ratio: float,
    today: date,
    portfolio_nav: float,
    calc_quantity_from_notional: Callable[[str, float], int],
) -> List[Order]:
    """
    インバースETFのヘッジ注文を生成する。

    Args:
        inverse_symbol: インバースETFのシンボル（例: "1357.T"）
        hedge_ratio: ヘッジ比率（0.0 ~ 1.0）
        today: 取引日
        portfolio_nav: ポートフォリオの評価額
        calc_quantity_from_notional: 金額から株数を計算する関数
            (symbol: str, notional: float) -> int

    Returns:
        注文オブジェクトのリスト
    """
    if hedge_ratio <= 0:
        return []

    notional = portfolio_nav * hedge_ratio
    qty = calc_quantity_from_notional(symbol=inverse_symbol, notional=notional)
    
    if qty == 0:
        return []

    return [
        Order(
            symbol=inverse_symbol,
            side="BUY",
            qty=qty,
            order_type="MOC",  # Market On Close 的な扱い
            comment=f"EventGuard hedge {hedge_ratio:.2f}",
        )
    ]


# ============================================================================
# 日次ドライバ統合例（疑似コード）
# ============================================================================
"""
日次ドライバ側での Event Guard 統合例:

from datetime import date
from event_guard import EventGuard
from order_builder import build_inverse_orders, Order


def daily_process(today: date, prices, universe_symbols):
    guard = EventGuard()

    # 1) 決算銘柄をユニバースから除外
    excluded = guard.get_excluded_symbols(today)
    tradable_symbols = [s for s in universe_symbols if s not in excluded]

    # 2) 通常戦略のターゲットウェイトを計算（equity01既存ロジック）
    alpha_weights = calc_alpha_weights(
        today=today,
        prices=prices,
        symbols=tradable_symbols,
    )  # dict[symbol] -> weight

    # 3) Event Guard からヘッジ比率を取得
    hedge_ratio = guard.get_hedge_ratio(today)

    # 4) 注文生成
    orders = []

    # 4-1) 通常戦略の注文
    orders.extend(build_orders_from_weights(alpha_weights))

    # 4-2) ヘッジ用インバースETFの注文
    if hedge_ratio > 0:
        portfolio_nav = get_portfolio_nav(today)
        orders.extend(build_inverse_orders(
            inverse_symbol=guard.inverse_symbol,
            hedge_ratio=hedge_ratio,
            today=today,
            portfolio_nav=portfolio_nav,
            calc_quantity_from_notional=calc_quantity_from_notional,
        ))

    # 5) 引け成行で発注
    send_orders_at_close(orders)
"""

