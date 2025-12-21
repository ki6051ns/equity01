# horizon_ensemble_variant_cross4.parquet 生成元の分析

## 生成スクリプト

`scripts/analysis/ensemble_variant_cross4.py` が `horizon_ensemble_variant_cross4.parquet` を生成している。

## 生成フロー

### 1. 入力データ

各horizon×variantのバックテスト結果を読み込む：
- `paper_trade_h{h}_{ladder_type}_{suffix}.parquet` または
- `paper_trade_with_alpha_beta_h{h}_{ladder_type}_{suffix}.parquet`

### 2. port_ret_cc の生成元

`ensemble_variant_cross4.py` は直接 port_ret_cc を計算していない。
代わりに、`paper_trade_*.parquet` から読み込んでいる。

`paper_trade_*.parquet` の `port_ret_cc` がどのように計算されているかは、`scripts/tools/paper_trade.py` を確認する必要がある。

### 3. paper_trade.py でのreturn定義

`scripts/tools/paper_trade.py:114` より：

```python
# 翌日リターン（forward 1d return, CLOSE→CLOSE）
prices["ret_fwd_1d"] = (
    prices.groupby(cfg.symbol_col)["close"].pct_change().shift(-1)
)
```

**重要**: `pct_change().shift(-1)` なので、**ret_fwd_1d[t] = (close[t+1] - close[t]) / close[t]**

これは「当日close → 翌日close」のリターンであり、**look-aheadが混入している可能性がある**。

### 4. アンサンブル合成

`ensemble_variant_cross4.py` では：
1. 各horizonのvariantを重み付き平均化（rank 75% + zdownvol 25%）
2. 各horizonを重み付き平均化（H1: 15%, H5: 15%, H10: 20%, H60: 10%, H90: 20%, H120: 20%）
3. 日付でマージ（`how="outer"`）→ `fillna(0.0)` で欠損を埋める

**問題点**:
- `paper_trade.py` の `ret_fwd_1d` が look-ahead を含んでいる可能性
- 日付マージ時の `fillna(0.0)` が不適切な場合がある
- `ffill().bfill()` でTOPIXリターンを補完しているが、これも日付ズレの原因になり得る

## 結論

`horizon_ensemble_variant_cross4.parquet` の `port_ret_cc` は、以下の問題を含む可能性がある：

1. **look-ahead混入**: `paper_trade.py` の `ret_fwd_1d = pct_change().shift(-1)` が当日に翌日の情報を使用
2. **日付カレンダー処理**: `outer` join + `fillna(0.0)` による不適切な補完
3. **TOPIX補完**: `ffill().bfill()` による不適切な補完

## 修正方針（採用）

`eval_stop_regimes.py` では、`horizon_ensemble_variant_cross4.parquet` から読み込むのではなく、
`daily_portfolio_guarded + prices` から毎回再構築して使用する。

これにより：
- **入力リークを物理的に遮断**
- **正しいreturn定義（w[t-1] * r[t]）を強制**
- **日付カレンダー処理の問題を回避**

