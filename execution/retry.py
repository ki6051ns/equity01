"""
retry.py

リトライデコレータ（簡易版）。
"""
import time
from functools import wraps
from typing import Callable, Type, Tuple

from execution.exceptions import RetryableError, FatalError


def retry_with_backoff(
    max_retries: int = 3,
    backoff_sec: float = 2.0,
    timeout_sec: float = 10.0,
):
    """
    リトライデコレータ（指数バックオフ）。
    
    Parameters
    ----------
    max_retries : int
        最大リトライ回数
    backoff_sec : float
        バックオフ秒数（指数バックオフのベース）
    timeout_sec : float
        タイムアウト秒数（未使用、将来の拡張用）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except FatalError as e:
                    # リトライ不可なエラーは即中断
                    raise
                except RetryableError as e:
                    last_exception = e
                    if attempt < max_retries:
                        # 指数バックオフ
                        wait_time = backoff_sec * (2 ** attempt)
                        time.sleep(wait_time)
                        continue
                    else:
                        # リトライ上限に達した
                        raise
                except Exception as e:
                    # 予期しない例外はFatalErrorとして扱う
                    raise FatalError(f"予期しないエラー: {e}", error_code="UNEXPECTED") from e
            
            # ここに来ることはないが、型チェッカーのため
            if last_exception:
                raise last_exception
            raise RuntimeError("リトライに失敗しました")
        
        return wrapper
    return decorator

