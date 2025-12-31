"""
write_order_intent.py

order_intentをCSV/Parquetに出力する。
SKIP時はorder_intent_{today}_SKIP.csvを出力。
"""
from pathlib import Path
from datetime import date, datetime

import pandas as pd


class OrderIntentWriter:
    """order_intentを出力する"""
    
    def __init__(self, output_dir: Path = Path("execution/execution_outputs")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write(self, df: pd.DataFrame, latest_date: pd.Timestamp, format: str = "both") -> None:
        """
        order_intentを出力する。
        
        Parameters
        ----------
        df : pd.DataFrame
            order_intent DataFrame
        latest_date : pd.Timestamp
            最新日
        format : str
            出力形式（"csv", "parquet", "both"）
        """
        date_str = latest_date.strftime("%Y%m%d")
        
        if format in ("csv", "both"):
            csv_path = self.output_dir / f"order_intent_{date_str}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"order_intentをCSVに出力: {csv_path}")
        
        if format in ("parquet", "both"):
            parquet_path = self.output_dir / f"order_intent_{date_str}.parquet"
            df.to_parquet(parquet_path, index=False)
            print(f"order_intentをParquetに出力: {parquet_path}")
            
            # latestシンボリックリンク（Windowsではコピー）
            latest_path = self.output_dir / "latest_order_intent.parquet"
            if latest_path.exists():
                latest_path.unlink()
            import shutil
            shutil.copy(parquet_path, latest_path)
    
    def write_skip(self, latest_date: pd.Timestamp, reason: str) -> None:
        """
        SKIP時のログファイルを出力する。
        
        Parameters
        ----------
        latest_date : pd.Timestamp
            最新日
        reason : str
            スキップ理由
        """
        today_str = datetime.now().strftime("%Y%m%d")
        skip_path = self.output_dir / f"order_intent_{today_str}_SKIP.csv"
        
        df_skip = pd.DataFrame({
            "latest_date": [latest_date.strftime("%Y-%m-%d")],
            "skip_reason": [reason],
            "checked_at": [datetime.now().isoformat()],
        })
        df_skip.to_csv(skip_path, index=False, encoding="utf-8-sig")
        print(f"SKIPログを出力: {skip_path}")


if __name__ == "__main__":
    # テスト
    df = pd.DataFrame({
        "latest_date": ["2025-01-01"],
        "symbol": ["7203.T", "6758.T"],
        "prev_weight": [0.1, 0.2],
        "target_weight": [0.15, 0.18],
        "delta_weight": [0.05, -0.02],
    })
    writer = OrderIntentWriter()
    writer.write(df, pd.Timestamp("2025-01-01"))
    
    # SKIPテスト
    writer.write_skip(pd.Timestamp("2025-01-01"), "latest_date unchanged")

