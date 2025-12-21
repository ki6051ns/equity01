# eval_stop_regimes.py と backtest_from_weights_with_stop.py の差分原因と修正内容

## 概要

`eval_stop_regimes.py`（eval系）と `backtest_from_weights_with_stop.py`（weights系）の出力が一致しない原因を特定し、修正を実施しました。

## 差分原因の分類

### 1. 価格データの差異
- **原因**: `backtest_from_weights_with_stop.py`が`close`を使用していた（`adj_close`を使用すべき）
- **影響**: 株式分割等の調整が反映されないため、リターンが不一致になる可能性がある

### 2. 日付アラインの不一致
- **原因**: `backtest_from_weights_with_stop.py`が`w[t] * r[t+1]`を使用していた（正しくは`w[t-1] * r[t]`）
- **影響**: 日付のインデックスが1つずれるため、結果が一致しない

### 3. STOP条件計算の不一致
- **原因**: `build_cross4_target_weights_with_stop.py`と`eval_stop_regimes.py`で異なるソースからreturnsを読み込んでいた
- **影響**: STOP条件が異なるため、STOP期間が一致せず、累積リターンが異なる

## 修正内容

### 1. `backtest_from_weights_with_stop.py`の修正

#### 価格データの修正
- **ファイル**: `scripts/analysis/backtest_from_weights_with_stop.py`
- **行**: 205-210
- **変更内容**: `close`から`adj_close`への変更（`adj_close`が存在する場合）

```python
# 修正前
prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()

# 修正後
if "adj_close" in prices_df.columns:
    prices_df["ret_1d"] = prices_df.groupby("symbol")["adj_close"].pct_change()
else:
    prices_df["ret_1d"] = prices_df.groupby("symbol")["close"].pct_change()
```

#### 日付アラインの修正
- **ファイル**: `scripts/analysis/backtest_from_weights_with_stop.py`
- **行**: 242-289
- **変更内容**: `w[t] * r[t+1]`から`w[t-1] * r[t]`への変更

```python
# 修正前
for i, date in enumerate(dates):
    weights_day = df_weights[df_weights["date"] == date].copy()
    next_date = dates[i + 1]
    # ... w[date] * r[next_date] を計算

# 修正後
for i, date in enumerate(dates):
    if i == 0:
        continue
    prev_date = dates[i - 1]
    weights_day = df_weights[df_weights["date"] == prev_date].copy()
    # ... w[prev_date] * r[date] を計算
```

### 2. `build_cross4_target_weights_with_stop.py`の修正

#### STOP条件計算の統一
- **ファイル**: `scripts/analysis/build_cross4_target_weights_with_stop.py`
- **行**: 79-204
- **変更内容**: `load_cross4_returns_for_stop()`を`rebuild_port_ret_from_weights()`を使うように修正

```python
# 修正後（デフォルトでrebuild_port_ret_from_weights()を使用）
if force_rebuild:
    from scripts.analysis.rebuild_port_ret_from_weights import rebuild_port_ret_from_weights
    port_ret = rebuild_port_ret_from_weights(use_adj_close=True, use_weight_lag=True)
    # ... TOPIXリターンとマージ
```

これにより、`eval_stop_regimes.py`と`build_cross4_target_weights_with_stop.py`で同じSTOP条件が使われるようになりました。

### 3. ドキュメントの作成

#### `docs/return_definition.md`の作成
- ポートフォリオリターンの定義を明文化
- `r_i[t] = adj_close_i[t] / adj_close_i[t-1] - 1`
- `port_ret[t] = sum_i w_i[t-1] * r_i[t]`
- STOP条件の定義も明文化

#### コードへの参照追加
- `backtest_from_weights_with_stop.py`: `docs/return_definition.md`への参照を追加
- `eval_stop_regimes.py`: STOP条件の定義をコメントに追加

### 4. デバッグスクリプトの作成

#### `debug_eval_vs_weights_day.py`の作成
- 指定日±数日のポートフォリオリターンを比較
- 差分の原因を分解（日付アライン、STOPフラグ不一致、欠損埋め等）
- Top寄与銘柄を表示（weights側のみ）

## 定義の統一

すべての実装は以下の定義に従うようになりました（`docs/return_definition.md`参照）：

1. **リターン計算**: `r_i[t] = adj_close_i[t] / adj_close_i[t-1] - 1`
2. **ポートフォリオリターン**: `port_ret[t] = sum_i w_i[t-1] * r_i[t]`
3. **STOP条件**: 
   - `alpha[t] = port_ret[t] - tpx_ret[t]`
   - `roll_alpha[t] = sum_{k=t-window}^{t-1} alpha[k]`
   - `roll_tpx[t] = sum_{k=t-window}^{t-1} tpx_ret[k]`
   - `stop_flag[t] = (roll_alpha[t] < 0) & (roll_tpx[t] < 0)`

## テスト結果（予想）

修正後、以下の比較がPASSするはずです：

- `stop0 w60`: `max_abs_diff < 1e-8`
- `stop0 w120`: `max_abs_diff < 1e-8`
- `planA w60`: `max_abs_diff < 1e-8`
- `planA w120`: `max_abs_diff < 1e-8`
- `planB w60`: `max_abs_diff < 1e-8`
- `planB w120`: `max_abs_diff < 1e-8`

## 次のステップ

1. 修正後のコードで`backtest_from_weights_with_stop.py`を再実行
2. `compare_eval_vs_weights_stop.py`で比較を実行し、PASSを確認
3. 特定日の差分が大きい場合は`debug_eval_vs_weights_day.py`で詳細分析

## 重要な注意事項

- **weights側の定義（w[t-1]*r[t]）を崩さない**: この定義は正しい実装の基準として維持されています
- **当日ターゲットウェイトを当日リターンに掛けない（ルックアヘッド）**: これは禁止されています

