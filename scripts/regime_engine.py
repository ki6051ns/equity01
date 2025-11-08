"""
レジームエンジン
HMM・BOCPD・Logitを使用して市場レジームを検出
"""

import pandas as pd
from pathlib import Path


class RegimeEngine:
    """市場レジームを検出するクラス"""
    
    def __init__(self, models_dir: str = "models/regime"):
        self.models_dir = Path(models_dir)
    
    def detect_regime_hmm(self, data: pd.DataFrame) -> pd.Series:
        """HMMを使用してレジームを検出"""
        pass
    
    def detect_regime_bocpd(self, data: pd.DataFrame) -> pd.Series:
        """BOCPDを使用してレジームを検出"""
        pass
    
    def detect_regime_logit(self, data: pd.DataFrame) -> pd.Series:
        """Logitを使用してレジームを検出"""
        pass
    
    def get_current_regime(self, features: pd.DataFrame) -> str:
        """現在のレジームを取得"""
        pass

