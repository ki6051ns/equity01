"""
executor/log_writer.py

RunLog出力補助（OrderIntent CSV出力等）
"""
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

from executor.models import RunLog


def write_order_intent_csv(
    run: RunLog,
    output_dir: Path = None,
) -> Path:
    """
    OrderIntentをCSV出力（監査・差分比較用）
    
    Parameters
    ----------
    run : RunLog
        実行ログ
    output_dir : Path or None
        出力ディレクトリ（デフォルト: executor_runs/intents）
    
    Returns
    -------
    Path
        出力したファイルのパス
    """
    if output_dir is None:
        output_dir = Path("executor_runs") / "intents"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # OrderIntentをDataFrameに変換
    if not run.order_intents:
        # 空の場合は空のCSVを出力
        df = pd.DataFrame()
        output_path = output_dir / f"order_intent_{run.run_id}.csv"
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path
    
    # 必要な列を抽出
    rows = []
    for intent in run.order_intents:
        rows.append({
            "order_key": intent.get("order_key"),
            "date": intent.get("date"),
            "account": intent.get("account"),
            "symbol": intent.get("symbol"),
            "side": intent.get("side"),
            "qty": intent.get("qty"),
            "notional": intent.get("notional"),
            "price_ref": intent.get("price_ref"),
            "reason": intent.get("reason"),
            "prev_weight": intent.get("prev_weight"),
            "target_weight": intent.get("target_weight"),
            "delta_weight": intent.get("delta_weight"),
            "notes": intent.get("notes", ""),
        })
    
    df = pd.DataFrame(rows)
    output_path = output_dir / f"order_intent_{run.run_id}.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    
    return output_path

