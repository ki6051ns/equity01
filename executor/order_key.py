"""
executor/order_key.py

order_key生成（冪等性確保）
date|account|symbol|side|qty|price_refからdeterministicなkeyを生成。
"""
import hashlib
from datetime import date


def generate_order_key(
    order_date: date,
    account: str,
    symbol: str,
    side: str,
    qty: int,
    price_ref: str,
) -> str:
    """
    deterministicなorder_keyを生成
    
    Parameters
    ----------
    order_date : date
        注文日
    account : str
        口座タイプ（"cash" | "cfd"）
    symbol : str
        銘柄コード
    side : str
        売買区分（"buy" | "sell"）
    qty : int
        数量
    price_ref : str
        価格参照方法（"last" | "close"）
    
    Returns
    -------
    str
        order_key（ハッシュ値、先頭16文字）
    """
    # 文字列を連結してハッシュ化
    key_str = f"{order_date.isoformat()}|{account}|{symbol}|{side}|{qty}|{price_ref}"
    key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    return key_hash[:16]

