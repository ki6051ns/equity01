"""
executor/adapters/sbi_cfd.py

SBI証券 CFD取引アダプター
"""
from typing import Optional, Dict, Any, List
from datetime import date
from executor.models import OrderIntent
from executor.adapters.result import AdapterResult


class SBICFDAdapter:
    """
    SBI証券 CFD取引アダプター
    
    CFD取引のUI操作・発注処理を担当。
    PRE_SUBMITモード: 注文画面まで進み、最終クリックだけ実行しない。
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Parameters
        ----------
        config : dict or None
            アダプター設定
        """
        self.config = config or {}
        self.driver = None  # Selenium WebDriver（実装時に追加）
    
    def login(self) -> bool:
        """
        ログイン
        
        Returns
        -------
        bool
            ログイン成功したか
        """
        # TODO: Selenium実装
        return False  # 未実装
    
    def select_account(self, account_type: str = "cfd") -> bool:
        """
        口座選択（CFD）
        
        Parameters
        ----------
        account_type : str
            口座タイプ（"cfd"固定）
        
        Returns
        -------
        bool
            選択成功したか
        """
        # TODO: Selenium実装
        return False  # 未実装
    
    def navigate_to_order_page(self) -> bool:
        """
        注文画面に遷移
        
        Returns
        -------
        bool
            遷移成功したか
        """
        # TODO: Selenium実装
        return False  # 未実装
    
    def fill_order_form(
        self,
        intent: OrderIntent,
    ) -> Dict[str, Any]:
        """
        注文フォームに入力
        
        Parameters
        ----------
        intent : OrderIntent
            注文意図
        
        Returns
        -------
        dict
            入力結果（success, details）
        """
        # TODO: Selenium実装
        # - 銘柄コード入力（CFD商品コード）
        # - 売買選択（buy/sell）
        # - 数量入力（lot単位）
        # - 価格タイプ選択（market/limit）
        return {
            "success": False,
            "details": {
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "message": "未実装",
            }
        }
    
    def enter_password(self, password: str) -> bool:
        """
        取引実行パスワード入力
        
        Parameters
        ----------
        password : str
            取引実行パスワード
        
        Returns
        -------
        bool
            入力成功したか
        """
        # TODO: Selenium実装
        return False  # 未実装
    
    def get_ui_reflection(self) -> Dict[str, Any]:
        """
        UI反映結果を取得（PRE_SUBMIT時点）
        
        Returns
        -------
        dict
            UI反映結果
        """
        # TODO: Selenium実装
        return {
            "symbol": None,
            "side": None,
            "qty": None,
            "price": None,
            "screenshot_path": None,
            "dom_dump": None,
        }
    
    def submit_order(self) -> Dict[str, Any]:
        """
        注文確定クリック（LIVE_SUBMIT時のみ）
        
        Warning
        -------
        PRE_SUBMITモードでは呼ばれない（dryrun.pyでガード）
        """
        # TODO: Selenium実装
        return {
            "success": False,
            "order_id": None,
            "error": "未実装",
        }
    
    def get_account_snapshot(self) -> Dict[str, Any]:
        """
        口座スナップショット取得（証拠金情報）
        
        Returns
        -------
        dict
            口座情報（available_margin, maintenance_ratio等）
        """
        # TODO: Selenium実装
        # - 口座情報画面に遷移
        # - 利用可能証拠金を取得
        # - 維持率を取得
        return {
            "available_margin": None,
            "maintenance_ratio": None,
            "total_margin": None,
            "snapshot_time": None,
        }
    
    def execute_pre_submit(
        self,
        intents: List[OrderIntent],
    ) -> AdapterResult:
        """
        PRE_SUBMIT実行（スタブ実装）
        
        注文画面まで進み、最終クリックだけ実行しない。
        UI自動化未実装のため、擬似ログを返す。
        
        Parameters
        ----------
        intents : list[OrderIntent]
            注文意図のリスト
        
        Returns
        -------
        AdapterResult
            実行結果（PRE_SUBMIT時点の状態）
        """
        # スタブ実装: UI反映の擬似ログを返す
        orders_reflected = []
        for intent in intents:
            orders_reflected.append({
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "notional": intent.notional,
                "reflected": True,  # スタブでは常にTrue
            })
        
        return AdapterResult(
            success=True,
            stop_reason="STOP_BEFORE_SUBMIT",
            ui_reflection_details={
                "order_reflected": True,
                "orders": orders_reflected,
                "screenshot_path": None,  # TODO: 実装時に設定
                "dom_dump": None,  # TODO: 実装時に設定
            },
        )
    
    def close(self):
        """リソース解放（WebDriver終了等）"""
        if self.driver is not None:
            # TODO: driver.quit()
            pass

