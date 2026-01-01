"""
executor/precheck.py

事前チェック（precheck）
休日・余力・価格鮮度・通信をチェックし、実行可否を判定。
"""
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from datetime import date, datetime
import pandas as pd
from dataclasses import dataclass

# プロジェクトルートをパスに追加
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class PrecheckResult:
    """事前チェック結果"""
    passed: bool
    reason: str  # チェック通過理由 or 停止理由
    details: Dict[str, Any]  # 詳細情報
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


def load_trading_calendar() -> pd.Series:
    """
    calendar正本を読み込む（index_tpx_daily.parquet の date）
    
    Returns
    -------
    pd.Series
        TPX営業日の日付系列（昇順、timezoneなし）
    """
    data_dir = PROJECT_ROOT / "data"
    tpx_path = data_dir / "index_tpx_daily.parquet"
    
    if not tpx_path.exists():
        # 代替パスを試す
        tpx_path = data_dir / "processed" / "index_tpx_daily.parquet"
        if not tpx_path.exists():
            raise FileNotFoundError(f"calendar正本が見つかりません: {tpx_path}")
    
    df_tpx = pd.read_parquet(tpx_path)
    
    # dateカラムを確認
    date_col = None
    for col in ["date", "trade_date"]:
        if col in df_tpx.columns:
            date_col = col
            break
    
    if date_col is None:
        raise ValueError(f"dateカラムが見つかりません。カラム: {df_tpx.columns.tolist()}")
    
    dates = pd.to_datetime(df_tpx[date_col]).dt.normalize()
    dates = dates.drop_duplicates().sort_values().reset_index(drop=True)
    
    return dates


def check_trading_day(target_date: date) -> PrecheckResult:
    """
    休日チェック
    
    Parameters
    ----------
    target_date : date
        チェック対象日
    
    Returns
    -------
    PrecheckResult
        チェック結果
    """
    try:
        calendar = load_trading_calendar()
        target_datetime = pd.Timestamp(target_date).normalize()
        
        is_trading_day = target_datetime in calendar.values
        
        if is_trading_day:
            return PrecheckResult(
                passed=True,
                reason="trading_day",
                details={"target_date": target_date.isoformat(), "is_trading_day": True}
            )
        else:
            return PrecheckResult(
                passed=False,
                reason="non_trading_day",
                details={
                    "target_date": target_date.isoformat(),
                    "is_trading_day": False,
                    "calendar_range": {
                        "min": calendar.min().isoformat() if len(calendar) > 0 else None,
                        "max": calendar.max().isoformat() if len(calendar) > 0 else None,
                    }
                }
            )
    except Exception as e:
        # カレンダー読み込み失敗時は警告を出して続行（Fail-safe原則に基づき）
        return PrecheckResult(
            passed=False,
            reason="calendar_load_error",
            details={"error": str(e), "target_date": target_date.isoformat()}
        )


def check_available_cash(
    required_cash: float,
    available_cash: Optional[float] = None,
    cash_buffer: float = 200_000.0,
) -> PrecheckResult:
    """
    現物買付余力チェック
    
    Parameters
    ----------
    required_cash : float
        必要現金額
    available_cash : float or None
        利用可能現金（Noneの場合はチェックスキップ）
    cash_buffer : float
        現金バッファ（常に残す額）
    
    Returns
    -------
    PrecheckResult
        チェック結果
    """
    if available_cash is None:
        return PrecheckResult(
            passed=True,
            reason="cash_check_skipped",
            details={"message": "available_cashが指定されていないためスキップ"}
        )
    
    available_after_buffer = available_cash - cash_buffer
    sufficient = available_after_buffer >= required_cash
    
    if sufficient:
        return PrecheckResult(
            passed=True,
            reason="cash_sufficient",
            details={
                "required_cash": required_cash,
                "available_cash": available_cash,
                "cash_buffer": cash_buffer,
                "available_after_buffer": available_after_buffer,
            }
        )
    else:
        return PrecheckResult(
            passed=False,
            reason="cash_insufficient",
            details={
                "required_cash": required_cash,
                "available_cash": available_cash,
                "cash_buffer": cash_buffer,
                "available_after_buffer": available_after_buffer,
                "shortfall": required_cash - available_after_buffer,
            }
        )


def check_available_margin(
    required_margin: float,
    available_margin: Optional[float] = None,
    margin_buffer_ratio: float = 0.25,
) -> PrecheckResult:
    """
    CFD必要証拠金チェック
    
    Parameters
    ----------
    required_margin : float
        必要証拠金
    available_margin : float or None
        利用可能証拠金（Noneの場合はチェックスキップ）
    margin_buffer_ratio : float
        マージン余裕比率（25% = 1.25倍必要）
    
    Returns
    -------
    PrecheckResult
        チェック結果
    """
    if available_margin is None:
        return PrecheckResult(
            passed=True,
            reason="margin_check_skipped",
            details={"message": "available_marginが指定されていないためスキップ"}
        )
    
    required_with_buffer = required_margin * (1.0 + margin_buffer_ratio)
    sufficient = available_margin >= required_with_buffer
    
    if sufficient:
        return PrecheckResult(
            passed=True,
            reason="margin_sufficient",
            details={
                "required_margin": required_margin,
                "required_with_buffer": required_with_buffer,
                "available_margin": available_margin,
                "margin_buffer_ratio": margin_buffer_ratio,
            }
        )
    else:
        return PrecheckResult(
            passed=False,
            reason="margin_insufficient",
            details={
                "required_margin": required_margin,
                "required_with_buffer": required_with_buffer,
                "available_margin": available_margin,
                "margin_buffer_ratio": margin_buffer_ratio,
                "shortfall": required_with_buffer - available_margin,
            }
        )


def check_price_freshness(
    symbol: str,
    price_date: date,
    target_date: date,
    stale_threshold_days: int = 2,
    stale_action: str = "SKIP",
) -> PrecheckResult:
    """
    価格鮮度チェック
    
    Parameters
    ----------
    symbol : str
        銘柄コード
    price_date : date
        価格の日付
    target_date : date
        目標日（最新日）
    stale_threshold_days : int
        許容遅延日数（デフォルト2日）
    stale_action : str
        古い場合の動作（"SKIP" | "HALT" | "USE_LAST"）
    
    Returns
    -------
    PrecheckResult
        チェック結果
    """
    delta_days = (target_date - price_date).days
    
    if delta_days <= stale_threshold_days:
        return PrecheckResult(
            passed=True,
            reason="price_fresh",
            details={
                "symbol": symbol,
                "price_date": price_date.isoformat(),
                "target_date": target_date.isoformat(),
                "delta_days": delta_days,
                "stale_threshold_days": stale_threshold_days,
            }
        )
    else:
        # 価格が古い
        if stale_action == "HALT":
            return PrecheckResult(
                passed=False,
                reason="price_stale_halt",
                details={
                    "symbol": symbol,
                    "price_date": price_date.isoformat(),
                    "target_date": target_date.isoformat(),
                    "delta_days": delta_days,
                    "stale_threshold_days": stale_threshold_days,
                    "stale_action": stale_action,
                }
            )
        elif stale_action == "USE_LAST":
            return PrecheckResult(
                passed=True,
                reason="price_stale_use_last",
                details={
                    "symbol": symbol,
                    "price_date": price_date.isoformat(),
                    "target_date": target_date.isoformat(),
                    "delta_days": delta_days,
                    "stale_threshold_days": stale_threshold_days,
                    "stale_action": stale_action,
                    "warning": "価格が古いがUSE_LAST設定により続行",
                }
            )
        else:  # SKIP
            return PrecheckResult(
                passed=False,
                reason="price_stale_skip",
                details={
                    "symbol": symbol,
                    "price_date": price_date.isoformat(),
                    "target_date": target_date.isoformat(),
                    "delta_days": delta_days,
                    "stale_threshold_days": stale_threshold_days,
                    "stale_action": stale_action,
                }
            )


def check_connectivity(
    test_url: Optional[str] = None,
    timeout_sec: float = 5.0,
) -> PrecheckResult:
    """
    通信チェック（簡易実装）
    
    Parameters
    ----------
    test_url : str or None
        テストURL（Noneの場合はチェックスキップ）
    timeout_sec : float
        タイムアウト（秒）
    
    Returns
    -------
    PrecheckResult
        チェック結果
    """
    if test_url is None:
        return PrecheckResult(
            passed=True,
            reason="connectivity_check_skipped",
            details={"message": "test_urlが指定されていないためスキップ"}
        )
    
    try:
        import urllib.request
        import urllib.error
        
        req = urllib.request.Request(test_url)
        req.add_header("User-Agent", "equity01-executor/1.0")
        
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            status_code = response.getcode()
            
            if 200 <= status_code < 300:
                return PrecheckResult(
                    passed=True,
                    reason="connectivity_ok",
                    details={
                        "test_url": test_url,
                        "status_code": status_code,
                        "timeout_sec": timeout_sec,
                    }
                )
            else:
                return PrecheckResult(
                    passed=False,
                    reason="connectivity_error",
                    details={
                        "test_url": test_url,
                        "status_code": status_code,
                        "timeout_sec": timeout_sec,
                    }
                )
    except urllib.error.URLError as e:
        return PrecheckResult(
            passed=False,
            reason="connectivity_error",
            details={
                "test_url": test_url,
                "error": str(e),
                "error_type": type(e).__name__,
                "timeout_sec": timeout_sec,
            }
        )
    except Exception as e:
        return PrecheckResult(
            passed=False,
            reason="connectivity_error",
            details={
                "test_url": test_url,
                "error": str(e),
                "error_type": type(e).__name__,
                "timeout_sec": timeout_sec,
            }
        )


def run_prechecks(
    target_date: date,
    required_cash: Optional[float] = None,
    required_margin: Optional[float] = None,
    available_cash: Optional[float] = None,
    available_margin: Optional[float] = None,
    cash_buffer: float = 200_000.0,
    margin_buffer_ratio: float = 0.25,
    connectivity_test_url: Optional[str] = None,
) -> Tuple[bool, List[PrecheckResult]]:
    """
    すべての事前チェックを実行
    
    Parameters
    ----------
    target_date : date
        対象日
    required_cash : float or None
        必要現金額
    required_margin : float or None
        必要証拠金
    available_cash : float or None
        利用可能現金
    available_margin : float or None
        利用可能証拠金
    cash_buffer : float
        現金バッファ
    margin_buffer_ratio : float
        マージン余裕比率
    connectivity_test_url : str or None
        通信テストURL
    
    Returns
    -------
    (all_passed, results)
        all_passed: すべてのチェックが通過したか
        results: チェック結果のリスト
    """
    results = []
    
    # 1. 休日チェック
    result = check_trading_day(target_date)
    results.append(result)
    if not result.passed:
        return False, results
    
    # 2. 現物買付余力チェック
    if required_cash is not None:
        result = check_available_cash(required_cash, available_cash, cash_buffer)
        results.append(result)
        if not result.passed:
            return False, results
    
    # 3. CFD必要証拠金チェック
    if required_margin is not None:
        result = check_available_margin(required_margin, available_margin, margin_buffer_ratio)
        results.append(result)
        if not result.passed:
            return False, results
    
    # 4. 通信チェック
    result = check_connectivity(connectivity_test_url)
    results.append(result)
    if not result.passed:
        return False, results
    
    return True, results

