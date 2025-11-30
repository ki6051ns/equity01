# scripts/paper_trade.py

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

import data_loader  # 既存の load_prices を利用

# プロジェクトルートをパスに追加（config を読むため）
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
import config  # type: ignore

STARTDATE = "2025-10-31"


@dataclass
class PaperTradeConfig:
    # build_portfolio.py の出力（EventGuard 適用後）
    portfolio_path: Path = Path("data/processed/daily_portfolio_guarded.parquet")

    # ポートフォリオ側のカラム名
    portfolio_date_col: str = "trading_date"  # 実際にポジションが有効になる日
    symbol_col: str = "symbol"
    weight_col: str = "weight"
    guard_factor_col: Optional[str] = "guard_factor"
    selected_col: Optional[str] = "selected"

    # プライス側（load_prices）のカラム名
    price_date_col: str = "date"

    # 年間営業日数（日本株想定）
    trading_days_per_year: int = 252

    # リスクフリー（とりあえず 0）
    risk_free_rate: float = 0.0

    # ペーパートレードとして集計する開始日（この日以降のみ Results に残す）
    # None にすると全期間を対象にする
    paper_trade_start_date: Optional[str] = STARTDATE


def prepare_forward_returns(cfg: PaperTradeConfig) -> pd.DataFrame:
    """
    prices から「翌日リターン（CLOSE→CLOSE）」を作成する。
    ret_fwd_1d: 当日 close → 翌営業日 close の単純リターン（t 時点にアライン）
    """
    prices = data_loader.load_prices().copy()

    # ログ用の軽い表示（挙動確認）
    print("load_prices() columns:", list(prices.columns))
    if cfg.symbol_col in prices.columns:
        syms = prices[cfg.symbol_col].unique()
        if len(syms) > 0:
            head_syms = " ".join(syms[:10])
            print(f"symbols: {head_syms} … (n= {len(syms)} )")
    print(
        prices[
            [
                c
                for c in [
                    cfg.price_date_col,
                    cfg.symbol_col,
                    "open",
                    "high",
                    "low",
                    "close",
                    "adj_close",
                    "volume",
                ]
                if c in prices.columns
            ]
        ].head()
    )

    # カラム存在チェック
    if cfg.price_date_col not in prices.columns:
        raise KeyError(
            f"{cfg.price_date_col!r} 列が必要です: {prices.columns.tolist()}"
        )

    if cfg.symbol_col not in prices.columns:
        # 万一 symbol_col が無い場合は単一銘柄としてフォールバック
        prices[cfg.symbol_col] = "SINGLE"

    # close 列が無ければ adj_close などから補完を試みる
    if "close" not in prices.columns:
        for cand in ["adj_close", "Adj Close", "Adj_Close", "ADJ_CLOSE"]:
            if cand in prices.columns:
                prices = prices.rename(columns={cand: "close"})
                break

    if "close" not in prices.columns:
        raise KeyError(f"'close' 列が必要です: {prices.columns.tolist()}")

    prices[cfg.price_date_col] = pd.to_datetime(prices[cfg.price_date_col])
    prices = prices.sort_values([cfg.symbol_col, cfg.price_date_col])

    # 翌日リターン（forward 1d return, CLOSE→CLOSE）
    prices["ret_fwd_1d"] = (
        prices.groupby(cfg.symbol_col)["close"].pct_change().shift(-1)
    )

    return prices[[cfg.price_date_col, cfg.symbol_col, "ret_fwd_1d"]]


def run_paper_trade(cfg: PaperTradeConfig) -> Tuple[pd.DataFrame, dict]:
    """
    daily_portfolio_guarded.parquet（guard 適用済みポートフォリオ）と
    forward 1日リターンを突き合わせ、日次の Return / 指標を算出する。
    PnL（実額）は内部計算のみで、出力には含めない。
    """
    # 1. ポートフォリオ読み込み
    df_port = pd.read_parquet(cfg.portfolio_path)

    # 日付カラムの解決（デフォルトは trading_date、無ければ date をフォールバック）
    if cfg.portfolio_date_col not in df_port.columns:
        if "trading_date" in df_port.columns:
            portfolio_date_col = "trading_date"
        elif "date" in df_port.columns:
            portfolio_date_col = "date"
        else:
            raise KeyError(
                f"ポートフォリオ側に {cfg.portfolio_date_col!r} も 'trading_date' も 'date' もありません: {df_port.columns.tolist()}"
            )
    else:
        portfolio_date_col = cfg.portfolio_date_col

    df_port[portfolio_date_col] = pd.to_datetime(df_port[portfolio_date_col])

    # selected があれば True のものだけに絞る
    if cfg.selected_col and cfg.selected_col in df_port.columns:
        before = len(df_port)
        df_port = df_port[df_port[cfg.selected_col]]
        print(f"selected フィルタ: {before} → {len(df_port)} rows")

    # guard_factor があれば weight に乗算
    if cfg.guard_factor_col and cfg.guard_factor_col in df_port.columns:
        df_port["_weight_eff"] = (
            df_port[cfg.weight_col] * df_port[cfg.guard_factor_col]
        )
    else:
        df_port["_weight_eff"] = df_port[cfg.weight_col]

    # 2. forward リターン作成
    df_ret = prepare_forward_returns(cfg)
    df_ret[cfg.price_date_col] = pd.to_datetime(df_ret[cfg.price_date_col])

    # 3. マージ（portfolio_date と price_date を突き合わせ）
    df_merged = df_port.merge(
        df_ret[[cfg.price_date_col, cfg.symbol_col, "ret_fwd_1d"]],
        left_on=[portfolio_date_col, cfg.symbol_col],
        right_on=[cfg.price_date_col, cfg.symbol_col],
        how="left",
        suffixes=("", "_px"),
    )

    # リターンが NaN の行は PnL 計算から除外（最終日など）
    df_merged = df_merged.dropna(subset=["ret_fwd_1d"])

    # 4. 銘柄別 PnL とヘッジフラグ（PnLは内部のみ）
    df_merged["pnl"] = df_merged["_weight_eff"] * df_merged["ret_fwd_1d"]
    INVERSE = config.INVERSE_HEDGE_SYMBOL
    df_merged["is_hedge"] = df_merged[cfg.symbol_col] == INVERSE

    # 5. 日次集計（ヘッジ/非ヘッジで分けて集計）
    # 5-1. ヘッジ/非ヘッジ別のPnL集計
    agg_pnl = (
        df_merged.groupby([portfolio_date_col, "is_hedge"])["pnl"]
        .sum()
        .unstack(fill_value=0.0)
    )

    # 列名整理：False=α側, True=ヘッジ側
    if False in agg_pnl.columns:
        agg_pnl = agg_pnl.rename(columns={False: "alpha_pnl"})
    else:
        agg_pnl["alpha_pnl"] = 0.0

    if True in agg_pnl.columns:
        agg_pnl = agg_pnl.rename(columns={True: "hedge_pnl"})
    else:
        agg_pnl["hedge_pnl"] = 0.0

    # その他の集計（gross_exposure / n_names は内部用。一応保持）
    agg_other = df_merged.groupby(portfolio_date_col).agg(
        gross_exposure=("_weight_eff", lambda x: x.abs().sum()),
        n_names=(cfg.symbol_col, "nunique"),
    )

    # 5-2. マージ
    df_daily = agg_pnl.join(agg_other, how="outer").fillna(0.0)
    df_daily["total_pnl"] = df_daily["alpha_pnl"] + df_daily["hedge_pnl"]

    # 5-3. NAVで割ってリターン化（初期元本を1.0とする）
    nav0 = 1.0
    df_daily["daily_return"] = df_daily["total_pnl"] / nav0
    df_daily["daily_return_alpha"] = df_daily["alpha_pnl"] / nav0
    df_daily["daily_return_hedge"] = df_daily["hedge_pnl"] / nav0

    df_daily = df_daily.sort_index()

    # 6. ペーパートレード開始日でフィルタ（live 期間だけを記録）
    if cfg.paper_trade_start_date:
        start_ts = pd.to_datetime(cfg.paper_trade_start_date)
        df_daily = df_daily.loc[df_daily.index >= start_ts]

    # 7. equity curve と drawdown（Returnベース）
    df_daily["equity"] = (1.0 + df_daily["daily_return"]).cumprod()

    if not df_daily.empty:
        rolling_max = df_daily["equity"].cummax()
        drawdown = df_daily["equity"] / rolling_max - 1.0
        df_daily["drawdown"] = drawdown
        max_dd = drawdown.min()
    else:
        df_daily["drawdown"] = np.nan
        max_dd = np.nan

    # 8. サマリ指標（Returnベース）
    ret_series = df_daily["daily_return"]
    mean_ret = ret_series.mean()
    vol = ret_series.std(ddof=0)

    if df_daily.empty or math.isnan(mean_ret) or math.isnan(vol) or vol == 0.0:
        ann_ret = np.nan
        ann_vol = np.nan
        sharpe = np.nan
    else:
        ann_ret = (1.0 + mean_ret) ** cfg.trading_days_per_year - 1.0
        ann_vol = vol * math.sqrt(cfg.trading_days_per_year)
        rf_daily = (1.0 + cfg.risk_free_rate) ** (
            1.0 / cfg.trading_days_per_year
        ) - 1.0
        sharpe = (mean_ret - rf_daily) / vol if vol != 0 else np.nan

    summary = {
        "n_days": int(df_daily.shape[0]),
        "ann_return": float(ann_ret)
        if not (isinstance(ann_ret, float) and math.isnan(ann_ret))
        else np.nan,
        "ann_vol": float(ann_vol)
        if not (isinstance(ann_vol, float) and math.isnan(ann_vol))
        else np.nan,
        "sharpe": float(sharpe)
        if not (isinstance(sharpe, float) and math.isnan(sharpe))
        else np.nan,
        "max_drawdown": float(max_dd)
        if not (isinstance(max_dd, float) and math.isnan(max_dd))
        else np.nan,
        "final_equity": float(df_daily["equity"].iloc[-1])
        if not df_daily.empty
        else np.nan,
    }

    # 9. 出力は Return 系だけに絞る
    df_out = df_daily[
        [
            "daily_return",
            "daily_return_alpha",
            "daily_return_hedge",
            "equity",
            "drawdown",
        ]
    ].copy()

    return df_out, summary


def main() -> None:
    cfg = PaperTradeConfig()

    df_daily, summary = run_paper_trade(cfg)

    out_path = Path("data/processed/paper_trade_daily.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # index（日付）付きで保存
    df_daily.to_csv(out_path)

    print("paper trade daily results saved to:", out_path)
    print(df_daily.tail())

    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
