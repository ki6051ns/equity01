"""
executor/build_intent.py

Intent生成（build_intent）
core成果物からOrderIntent/HedgeIntentを生成（execution/から完全独立）。

数量（qty）はexecutor側で確定（現実制約を考慮）。
"""
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import date
import hashlib
import pandas as pd

# プロジェクトルートをパスに追加
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from executor.models import OrderIntent, HedgeIntent, ExecutionConfig
from executor.config_loader import load_execution_config
from executor.order_key import generate_order_key

# data_loaderのインポート
try:
    from scripts.tools.lib import data_loader
except ImportError:
    try:
        from tools.lib import data_loader
    except ImportError:
        # 代替パスを試す
        tools_lib_path = PROJECT_ROOT / "scripts" / "tools" / "lib"
        if str(tools_lib_path.parent) not in sys.path:
            sys.path.insert(0, str(tools_lib_path.parent))
        from lib import data_loader


def read_latest_portfolio() -> pd.DataFrame:
    """
    core成果物（daily_portfolio_guarded.parquet）の最新日を読み込む
    
    Returns
    -------
    pd.DataFrame
        最新日のポートフォリオ（date, symbol, weight など）
    """
    portfolio_path = PROJECT_ROOT / "data" / "processed" / "daily_portfolio_guarded.parquet"
    
    if not portfolio_path.exists():
        raise FileNotFoundError(f"ポートフォリオファイルが見つかりません: {portfolio_path}")
    
    df = pd.read_parquet(portfolio_path)
    
    # date列をdatetimeに変換
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        latest_date = df["date"].max()
        df_latest = df[df["date"] == latest_date].copy()
    else:
        raise KeyError("'date' 列が見つかりません")
    
    return df_latest


def read_prev_weights() -> Optional[pd.Series]:
    """
    前日ウェイトを読み込む（簡易実装）
    
    TODO: executor_runs/state/に前日状態を保存する仕組みを追加
    
    Returns
    -------
    pd.Series or None
        前日ウェイト（symbol -> weight）。存在しない場合はNone
    """
    # 簡易実装: daily_portfolio_guarded.parquetから前日を取得
    portfolio_path = PROJECT_ROOT / "data" / "processed" / "daily_portfolio_guarded.parquet"
    
    if not portfolio_path.exists():
        return None
    
    df = pd.read_parquet(portfolio_path)
    
    if "date" not in df.columns:
        return None
    
    df["date"] = pd.to_datetime(df["date"])
    
    # 最新日と前日を取得
    dates = df["date"].unique()
    if len(dates) < 2:
        return None  # 前日が無い
    
    dates_sorted = sorted(dates)
    latest_date = dates_sorted[-1]
    prev_date = dates_sorted[-2]
    
    df_prev = df[df["date"] == prev_date]
    
    if "symbol" in df_prev.columns and "weight" in df_prev.columns:
        return df_prev.set_index("symbol")["weight"]
    
    return None


def calculate_qty_from_notional(
    notional: float,
    price: float,
    account: str,
    lot_size: int = 1,
) -> int:
    """
    notionalから数量（qty）を計算
    
    Parameters
    ----------
    notional : float
        目標notional
    price : float
        価格
    account : str
        口座タイプ（"cash" | "cfd"）
    lot_size : int
        単元（lot）サイズ（デフォルト1）
    
    Returns
    -------
    int
        数量（qty）
    """
    if price <= 0:
        return 0
    
    if account == "cash":
        # 現物: lot_size単位（通常は1株）
        qty = int(notional / price / lot_size) * lot_size
    else:  # cfd
        # CFD: lot単位（商品ごとに異なる、簡易実装）
        qty = int(notional / price / lot_size) * lot_size
        if qty < lot_size:
            qty = 0
    
    return max(qty, 0)


def calculate_rebalance_notional(
    target_weights: pd.Series,
    prev_weights: Optional[pd.Series],
    equity_value: float,
    prices: pd.Series,
    config: ExecutionConfig,
    available_cash: Optional[float] = None,
    available_margin: Optional[float] = None,
) -> pd.Series:
    """
    リバランスnotionalを計算（execution/build_order_intent.pyのロジックを踏襲）
    
    Parameters
    ----------
    target_weights : pd.Series
        ターゲットウェイト（symbol -> weight）
    prev_weights : pd.Series or None
        前日ウェイト（symbol -> weight）
    equity_value : float
        エクイティ価値（AUM * leverage_ratio）
    prices : pd.Series
        現在価格（symbol -> price）
    config : ExecutionConfig
        実行設定
    available_cash : float or None
        利用可能現金
    available_margin : float or None
        利用可能証拠金
    
    Returns
    -------
    pd.Series
        notional_delta（symbol -> notional_delta）
    """
    # 前日ウェイトが無い場合は0とみなす
    if prev_weights is None:
        prev_weights = pd.Series(0.0, index=target_weights.index)
    
    # 全銘柄のユニオンを取得
    all_symbols = target_weights.index.union(prev_weights.index).union(prices.index)
    all_symbols = all_symbols.sort_values()
    
    # 各銘柄のウェイトを取得（存在しない場合は0）
    prev_w = prev_weights.reindex(all_symbols, fill_value=0.0)
    target_w = target_weights.reindex(all_symbols, fill_value=0.0)
    price = prices.reindex(all_symbols, fill_value=0.0)
    
    # delta_weightを計算
    delta_w = target_w - prev_w
    
    # notional_deltaを計算（= equity_value * delta_weight）
    notional_delta = equity_value * delta_w
    
    # 1) 共通：上限制約でクリップ
    gross_notional = notional_delta.abs().sum()
    gross_notional_cap = config.aum * config.max_gross_notional_ratio
    
    if gross_notional > gross_notional_cap:
        scale = gross_notional_cap / gross_notional
        notional_delta = notional_delta * scale
    
    # 2) 現物（買付余力）
    if available_cash is None:
        available_cash = config.aum - config.cash_buffer_jpy
    
    buy_notional = notional_delta[notional_delta > 0].sum()
    if buy_notional > available_cash:
        # BUY側を縮小
        buy_scale = available_cash / buy_notional
        notional_delta = notional_delta.apply(lambda x: x * buy_scale if x > 0 else x)
    
    # 3) CFD（必要証拠金＋バッファ）
    if config.leverage_ratio > 1.0:
        gross_buy_notional = notional_delta[notional_delta > 0].abs().sum()
        req_margin_simple = gross_buy_notional / config.leverage_ratio
        req_margin_with_buffer = req_margin_simple * (1 + config.margin_buffer_ratio)
        
        if available_margin is None:
            available_margin = config.aum - config.cash_buffer_jpy
        
        if req_margin_with_buffer > available_margin:
            # notionalを縮小
            margin_scale = available_margin / req_margin_with_buffer
            notional_delta = notional_delta * margin_scale
    
    # 銘柄別上限チェック
    max_symbol_notional = config.aum * config.max_symbol_notional_ratio
    notional_delta = notional_delta.apply(lambda x: max(-max_symbol_notional, min(max_symbol_notional, x)))
    
    return notional_delta


def build_order_intents_from_core(
    latest_date: date,
    config: Optional[ExecutionConfig] = None,
    available_cash: Optional[float] = None,
    available_margin: Optional[float] = None,
) -> Tuple[List[OrderIntent], str]:
    """
    core成果物からOrderIntentを生成
    
    Parameters
    ----------
    latest_date : date
        最新日
    config : ExecutionConfig or None
        実行設定
    available_cash : float or None
        利用可能現金
    available_margin : float or None
        利用可能証拠金
    
    Returns
    -------
    (order_intents, input_file_hash)
        order_intents: OrderIntentのリスト
        input_file_hash: 入力ファイルのhash（再現性確保）
    """
    if config is None:
        config = load_execution_config()
    
    # 最新ポートフォリオを読み込み
    df_latest = read_latest_portfolio()
    
    # 入力ファイルhashを計算（再現性確保）
    portfolio_path = PROJECT_ROOT / "data" / "processed" / "daily_portfolio_guarded.parquet"
    with open(portfolio_path, "rb") as f:
        input_file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
    
    # 最新日を確認
    latest_datetime = pd.to_datetime(df_latest["date"].iloc[0]).normalize()
    if latest_datetime.date() != latest_date:
        raise ValueError(f"指定されたlatest_date ({latest_date}) とポートフォリオの最新日 ({latest_datetime.date()}) が一致しません")
    
    # 前日ウェイトを取得
    prev_weights = read_prev_weights()
    
    # 価格データを読み込み
    prices_df = data_loader.load_prices()
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    
    # 最新日の価格を取得
    latest_prices_df = prices_df[prices_df["date"] == latest_datetime]
    if latest_prices_df.empty:
        # 最新日が無い場合は最新の有効な日を取得
        latest_prices_df = (
            prices_df[prices_df["date"] <= latest_datetime]
            .sort_values("date")
            .groupby("symbol")
            .last()
            .reset_index()
        )
    
    if "symbol" in latest_prices_df.columns and "close" in latest_prices_df.columns:
        prices_series = latest_prices_df.set_index("symbol")["close"]
    else:
        raise ValueError("価格データが取得できません")
    
    # リバランスnotionalを計算
    equity_value = config.aum * config.leverage_ratio
    target_weights = df_latest.set_index("symbol")["weight"]
    notional_delta = calculate_rebalance_notional(
        target_weights=target_weights,
        prev_weights=prev_weights,
        equity_value=equity_value,
        prices=prices_series,
        config=config,
        available_cash=available_cash,
        available_margin=available_margin,
    )
    
    # OrderIntentに変換
    order_intents = []
    for symbol in notional_delta.index:
        delta = notional_delta[symbol]
        
        # 最小取引金額チェック
        if abs(delta) < config.min_trade_notional_jpy:
            continue
        
        side = "buy" if delta > 0 else "sell"
        notional = abs(delta)
        
        # 価格を取得
        price = prices_series.get(symbol, 0.0)
        if price <= 0:
            continue  # 価格が無効な場合はスキップ
        
        # 数量を計算
        account = "cash"  # デフォルトは現物（TODO: CFD対応）
        lot_size = config.lot_size_map.get(symbol, 1)  # デフォルト1株
        qty = calculate_qty_from_notional(notional, price, account, lot_size)
        
        if qty <= 0:
            continue  # 数量が0の場合はスキップ
        
        # order_keyを生成
        order_key = generate_order_key(
            order_date=latest_date,
            account=account,
            symbol=symbol,
            side=side,
            qty=qty,
            price_ref="close",
        )
        
        # 制約条件
        constraints = {
            "min_cash": config.cash_buffer_jpy,
            "max_leverage": config.leverage_ratio,
        }
        
        # メタデータ
        prev_w = prev_weights.get(symbol, 0.0) if prev_weights is not None else 0.0
        target_w = target_weights.get(symbol, 0.0)
        delta_w = target_w - prev_w
        
        # notes
        notes_parts = []
        if abs(delta_w) < 0.001:
            notes_parts.append("delta_weight < 0.1%")
        if target_w == 0.0 and prev_w > 0.0:
            notes_parts.append("exit")
        elif target_w > 0.0 and prev_w == 0.0:
            notes_parts.append("enter")
        notes = "; ".join(notes_parts) if notes_parts else ""
        
        # OrderIntentを作成
        intent = OrderIntent(
            date=latest_date,
            account=account,
            symbol=symbol,
            side=side,
            qty=qty,
            price_ref="close",
            reason="rebalance",
            constraints=constraints,
            notional=notional,
            order_key=order_key,
            prev_weight=prev_w,
            target_weight=target_w,
            delta_weight=delta_w,
            notes=notes,
        )
        order_intents.append(intent)
    
    return order_intents, input_file_hash


def build_hedge_intents_from_core(
    latest_date: date,
    config: Optional[ExecutionConfig] = None,
) -> List[HedgeIntent]:
    """
    core成果物からHedgeIntentを生成
    
    Parameters
    ----------
    latest_date : date
        最新日
    config : ExecutionConfig or None
        実行設定
    
    Returns
    -------
    list[HedgeIntent]
        HedgeIntentのリスト
    
    Note
    ----
    現在は簡易実装。β情報はcore成果物から取得する必要がある（TODO）。
    """
    if config is None:
        config = load_execution_config()
    
    hedge_intents = []
    
    # TODO: core成果物からβ情報を取得してヘッジintentを生成
    # 現在は空リストを返す
    
    return hedge_intents
