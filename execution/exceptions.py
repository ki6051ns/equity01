"""
exceptions.py

リトライ可能/不可能な例外を分類する。
"""
from typing import Optional


class ExecutionError(Exception):
    """execution関連の基底例外"""
    pass


class RetryableError(ExecutionError):
    """リトライ可能なエラー（タイムアウト、接続断、一時的5xx、レート制限）"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class FatalError(ExecutionError):
    """リトライ不可なエラー（注文パラメータ不正、建玉不足、口座制約違反、認証失敗）"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class TimeoutError(RetryableError):
    """タイムアウトエラー"""
    pass


class ConnectionError(RetryableError):
    """接続エラー"""
    pass


class RateLimitError(RetryableError):
    """レート制限エラー"""
    pass


class InvalidOrderError(FatalError):
    """注文パラメータ不正"""
    pass


class InsufficientPositionError(FatalError):
    """建玉不足エラー"""
    pass


class AccountConstraintError(FatalError):
    """口座制約違反エラー"""
    pass


class AuthenticationError(FatalError):
    """認証失敗エラー"""
    pass

