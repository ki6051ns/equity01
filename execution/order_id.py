"""
order_id.py

latest_date + symbol + side から deterministic な order_key を生成する。
run_idは含めない（冪等性のため）。
"""
import hashlib
from datetime import date
from typing import Optional


def generate_order_key(
    latest_date: date,
    symbol: str,
    side: str,  # "BUY" or "SELL"
    rounded_notional: Optional[float] = None,
) -> str:
    """
    deterministic な order_key を生成する。
    
    Parameters
    ----------
    latest_date : date
        最新日
    symbol : str
        銘柄コード
    side : str
        売買区分（"BUY" or "SELL"）
    rounded_notional : float or None
        丸めた取引金額（オプション、notionalが変わり得る場合に使用）
    
    Returns
    -------
    str
        order_key（SHA256ハッシュの先頭16文字）
    """
    # 正規化
    date_str = latest_date.strftime("%Y-%m-%d") if isinstance(latest_date, date) else str(latest_date)
    symbol_upper = symbol.upper().strip()
    side_upper = side.upper().strip()
    
    # 結合してハッシュ化（run_idは含めない）
    if rounded_notional is not None:
        # notionalを丸める（10万円単位）
        rounded = round(rounded_notional / 100_000) * 100_000
        key_string = f"{date_str}|{symbol_upper}|{side_upper}|{rounded}"
    else:
        key_string = f"{date_str}|{symbol_upper}|{side_upper}"
    
    hash_obj = hashlib.sha256(key_string.encode("utf-8"))
    order_key = hash_obj.hexdigest()[:16]  # 先頭16文字
    
    return order_key


if __name__ == "__main__":
    # テスト
    latest_date = date(2025, 1, 1)
    symbol = "7203.T"
    side = "BUY"
    
    key1 = generate_order_key(latest_date, symbol, side)
    key2 = generate_order_key(latest_date, symbol, side)
    
    print(f"order_key: {key1}")
    print(f"同一パラメータで再生成: {key2}")
    print(f"一致: {key1 == key2}")
    
    # run_idが違っても同じキーになることを確認
    key3 = generate_order_key(latest_date, symbol, side)
    print(f"run_id無関係で一致: {key1 == key3}")

