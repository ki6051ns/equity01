"""
データローダー
株価・出来高・為替・VIX・先物などの生データを読み込む
"""

import pandas as pd
from pathlib import Path


class DataLoader:
    """生データを読み込むクラス"""
    
    def __init__(self, data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)
    
    def load_stock_data(self, symbol: str) -> pd.DataFrame:
        """株価データを読み込む"""
        pass
    
    def load_volume_data(self, symbol: str) -> pd.DataFrame:
        """出来高データを読み込む"""
        pass
    
    def load_fx_data(self, pair: str = "USDJPY") -> pd.DataFrame:
        """為替データを読み込む"""
        pass
    
    def load_vix_data(self) -> pd.DataFrame:
        """VIXデータを読み込む"""
        pass
    
    def load_futures_data(self, contract: str) -> pd.DataFrame:
        """先物データを読み込む"""
        pass

