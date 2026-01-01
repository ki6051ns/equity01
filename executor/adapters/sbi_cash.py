"""
executor/adapters/sbi_cash.py

SBI証券 現物取引アダプター
"""
from typing import Optional, Dict, Any, List
from datetime import date
from executor.models import OrderIntent
from executor.adapters.result import AdapterResult


class SBICashAdapter:
    """
    SBI証券 現物取引アダプター
    
    現物取引のUI操作・発注処理を担当。
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
        # - ログイン画面にアクセス
        # - ID/PW入力
        # - 二要素認証対応
        # - ログイン成功を確認
        return False  # 未実装
    
    def select_account(self, account_type: str = "cash") -> bool:
        """
        口座選択（現物）
        
        Parameters
        ----------
        account_type : str
            口座タイプ（"cash"固定）
        
        Returns
        -------
        bool
            選択成功したか
        """
        # TODO: Selenium実装
        # - 口座選択画面に遷移
        # - 現物口座を選択
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
        # - 注文画面に遷移
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
        # - 銘柄コード入力
        # - 売買選択（buy/sell）
        # - 数量入力（qty）
        # - 価格タイプ選択（market/limit）
        # - 入力内容をDOMから取得して検証
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
        
        Note
        ----
        パスワードはログに絶対に残さない
        """
        # TODO: Selenium実装
        # - 取引実行パスワード入力フィールドに値を入力
        # - パスワードはメモリ上のみで、ログに出力しない
        return False  # 未実装
    
    def get_ui_reflection(self) -> Dict[str, Any]:
        """
        UI反映結果を取得（PRE_SUBMIT時点）
        
        Returns
        -------
        dict
            UI反映結果（symbol, side, qty, price等のDOMから取得した値）
        """
        # TODO: Selenium実装
        # - 注文画面のDOMから入力値を取得
        # - スクリーンショット取得（オプション）
        # - DOM dump取得（オプション）
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
        
        Returns
        -------
        dict
            発注結果（success, order_id等）
        
        Warning
        -------
        PRE_SUBMITモードでは呼ばれない（dryrun.pyでガード）
        """
        # TODO: Selenium実装
        # - 最終確認画面で「発注確定」ボタンをクリック
        # - 注文IDを取得
        # - エラーメッセージがあれば取得
        return {
            "success": False,
            "order_id": None,
            "error": "未実装",
        }
    
    def get_account_snapshot(self) -> Dict[str, Any]:
        """
        口座スナップショット取得（余力情報）
        
        Returns
        -------
        dict
            口座情報（available_cash, total_value等）
        """
        # TODO: Selenium実装
        # - 口座情報画面に遷移
        # - 買付余力を取得
        # - 口座残高を取得
        return {
            "available_cash": None,
            "total_value": None,
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

