# scripts/paper_trade.py

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

import data_loader  # 既存の load_prices を利用


@dataclass
class PaperTradeConfig:
    portfolio_path: Path = Path("data/processed/daily_portfolio_guarded.parquet")

    date_col: str = "date"
    symbol_col: str = "symbol"
    weight_col: str = "weight"

    # 年間営業日数（日本株想定）
    trading_days_per_year: int = 252

    # リスクフリーはとりあえず 0 とする
    risk_free_rate: float = 0.0


def prepare_forward_returns(cfg: PaperTradeConfig) -> pd.DataFrame:
    """
    prices から「翌日リターン」を作成する。
    ret_fwd_1d: 当日 close → 翌営業日 close の単純リターン
    """
    prices = data_loader.load_prices().copy()

    # カラム確認＆整形
    if cfg.date_col not in prices.columns:
        raise KeyError(f"'date' 列が必要です: {prices.columns.tolist()}")

    if cfg.symbol_col not in prices.columns:
        # 単一銘柄の場合のフォールバック
        prices[cfg.symbol_col] = "SINGLE"

    if "close" not in prices.columns:
        for cand in ["adj_close", "Adj Close", "Adj_Close", "ADJ_CLOSE"]:
            if cand in prices.columns:
                prices = prices.rename(columns={cand: "close"})
                break

    if "close" not in prices.columns:
        raise KeyError(f"'close' 列が必要です: {prices.columns.tolist()}")

    prices[cfg.date_col] = pd.to_datetime(prices[cfg.date_col])
    prices = prices.sort_values([cfg.symbol_col, cfg.date_col])

    # 翌日リターン（forward 1d return）
    # ret_fwd_1d[t] = close[t+1] / close[t] - 1
    def _fwd_ret(x: pd.Series) -> pd.Series:
        return x.shift(-1) / x - 1.0

    prices["ret_fwd_1d"] = prices.groupby(cfg.symbol_col)["close"].transform(_fwd_ret)

    return prices[[cfg.date_col, cfg.symbol_col, "ret_fwd_1d"]]


def run_paper_trade(cfg: PaperTradeConfig) -> Tuple[pd.DataFrame, dict]:
    """
    daily_portfolio と価格からペーパートレードを実行。
    戻り値:
      - df_daily: 日次の pnl / 累積カーブなど
      - summary: サマリ指標（dict）
    """
    # 1. ポートフォリオ読み込み
    df_port = pd.read_parquet(cfg.portfolio_path).copy()
    df_port[cfg.date_col] = pd.to_datetime(df_port[cfg.date_col])

    # weight が無ければ equal weight を仮定
    if cfg.weight_col not in df_port.columns:
        # 同一日の selected=True で均等割り
        df_port["selected"] = df_port.get("selected", True)

        def _assign_equal_w(g: pd.DataFrame) -> pd.DataFrame:
            g = g.copy()
            sel = g["selected"]
            n = sel.sum()
            if n > 0:
                w = 1.0 / n
                g.loc[sel, cfg.weight_col] = w
                g.loc[~sel, cfg.weight_col] = 0.0
            else:
                g[cfg.weight_col] = 0.0
            return g

        df_port = df_port.groupby(cfg.date_col, group_keys=False).apply(_assign_equal_w)

    # 2. 翌日リターンの準備
    df_ret = prepare_forward_returns(cfg)

    # 3. マージ（同一日・同一銘柄で join）
    df_merged = df_port.merge(
        df_ret,
        on=[cfg.date_col, cfg.symbol_col],
        how="left",
    )

    # 最終日など、返り値が NaN の行は PnL計算から除外
    df_merged = df_merged.dropna(subset=["ret_fwd_1d"])

    # 4. 銘柄別 PnL
    df_merged["pnl"] = df_merged[cfg.weight_col] * df_merged["ret_fwd_1d"]

    # 5. 日次集計
    df_daily = (
        df_merged
        .groupby(cfg.date_col)
        .agg(
            daily_return=("pnl", "sum"),
            gross_exposure=(cfg.weight_col, lambda x: x.abs().sum()),
            n_names=("pnl", "count"),
        )
        .sort_index()
    )

    # 累積リターン（equity curve）
    df_daily["equity"] = (1.0 + df_daily["daily_return"]).cumprod()

    # 最大ドローダウン
    rolling_max = df_daily["equity"].cummax()
    drawdown = df_daily["equity"] / rolling_max - 1.0
    df_daily["drawdown"] = drawdown
    max_dd = drawdown.min()

    # サマリ指標
    ret_series = df_daily["daily_return"]
    mean_ret = ret_series.mean()
    vol = ret_series.std(ddof=0)

    ann_ret = (1.0 + mean_ret) ** cfg.trading_days_per_year - 1.0 if not math.isnan(mean_ret) else np.nan
    ann_vol = vol * math.sqrt(cfg.trading_days_per_year) if not math.isnan(vol) else np.nan
    sharpe = (ann_ret - cfg.risk_free_rate) / ann_vol if ann_vol not in (0.0, np.nan) else np.nan

    summary = {
        "n_days": len(df_daily),
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "final_equity": df_daily["equity"].iloc[-1] if len(df_daily) > 0 else np.nan,
    }

    return df_daily, summary


def main():
    cfg = PaperTradeConfig()

    df_daily, summary = run_paper_trade(cfg)

    out_path = Path("data/processed/paper_trade_daily.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_daily.to_csv(out_path)

    print("paper trade daily results saved to:", out_path)
    print(df_daily.tail())

    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

