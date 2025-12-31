"""
state_store.py

前日スナップショット（execution側のstate）を管理する。
latest_date進行ガード（run_guard）も管理する。
state.json形式を使用。
"""
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

import pandas as pd


class StateStore:
    """前日スナップショットとlatest_date進行ガードを保存・読み込む"""
    
    def __init__(self, state_dir: Path = Path("execution/execution_state")):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "state.json"
        self.weights_file = self.state_dir / "latest_weights.parquet"  # 前回のweights保存用
    
    def save_state(self, df: pd.DataFrame, date: pd.Timestamp) -> None:
        """
        現在のポートフォリオ状態を保存する。
        
        Parameters
        ----------
        df : pd.DataFrame
            ポートフォリオ（date, symbol, weight など）
        date : pd.Timestamp
            保存する日付
        """
        # weightsを保存（前回実行時のweightsとして使用）
        if "symbol" in df.columns and "weight" in df.columns:
            df_weights = df[["symbol", "weight"]].copy()
            df_weights.to_parquet(self.weights_file, index=False)
    
    def load_state(self) -> Optional[pd.DataFrame]:
        """
        前日のポートフォリオ状態を読み込む。
        
        Returns
        -------
        pd.DataFrame or None
            前日の状態。存在しない場合はNone
        """
        if not self.weights_file.exists():
            return None
        
        return pd.read_parquet(self.weights_file)
    
    def get_prev_weights(self) -> Optional[pd.Series]:
        """
        前日のウェイト（symbolをインデックスとするSeries）を取得する。
        
        Returns
        -------
        pd.Series or None
            前日のウェイト（symbol -> weight）。存在しない場合はNone
        """
        df_state = self.load_state()
        if df_state is None or df_state.empty:
            return None
        
        if "symbol" not in df_state.columns or "weight" not in df_state.columns:
            return None
        
        return df_state.set_index("symbol")["weight"]
    
    def get_last_executed_latest_date(self) -> Optional[pd.Timestamp]:
        """
        前回実行時のlatest_dateを取得する（run_guard用）。
        
        Returns
        -------
        pd.Timestamp or None
            前回実行時のlatest_date。存在しない場合はNone
        """
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                date_str = state.get("last_executed_latest_date")
                if date_str:
                    return pd.to_datetime(date_str)
        except Exception:
            pass
        
        return None
    
    def save_last_executed_latest_date(self, latest_date: pd.Timestamp) -> None:
        """
        実行完了時のlatest_dateを保存する（run_guard用）。
        
        Parameters
        ----------
        latest_date : pd.Timestamp
            実行完了時のlatest_date
        """
        state = {
            "last_executed_latest_date": latest_date.strftime("%Y-%m-%d"),
            "last_run_at": datetime.now().isoformat(),
        }
        
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    store = StateStore()
    prev = store.get_prev_weights()
    if prev is not None:
        print(f"前日ウェイト: {len(prev)} 銘柄")
        print(prev.head())
    else:
        print("前日状態なし（初回実行）")
    
    last_date = store.get_last_executed_latest_date()
    if last_date is not None:
        print(f"\n前回実行時のlatest_date: {last_date.date()}")
    else:
        print("\n前回実行履歴なし")
