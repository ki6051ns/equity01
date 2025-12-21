# ポートフォリオリターンの定義

## 正しい定義（weights型）

### 基本定義

```
r_i[t] = adj_close_i[t] / adj_close_i[t-1] - 1

port_ret[t] = sum_i w_i[t-1] * r_i[t]
```

### 重要なポイント

1. **リターン計算**: `r_i[t]`は銘柄iのt日のリターン（前日比）
   - `adj_close_i[t]`（調整後終値）を使用
   - `adj_close_i[t-1]`（前日の調整後終値）で割る

2. **ウェイトの適用**: `w_i[t-1]`（前日のウェイト）を`r_i[t]`（当日のリターン）に掛ける
   - `w_i[t]`はt日の寄り付き前（前日引け後）に確定しているターゲット
   - 実運用では`w_i[t]`は`t+1`日に適用される
   - 実装上は`port_ret[t]`には`w[t-1]`が掛かる（正しい定義）

3. **日付アライン**:
   - t日のポートフォリオリターンは、`t-1`日のウェイトと`t`日のリターンから計算される
   - **禁止**: `w[t] * r[t]`（look-aheadバイアス）

## 実装での参照

この定義は以下のファイルで使用されます：

- `scripts/analysis/rebuild_port_ret_from_weights.py`: `rebuild_port_ret_from_weights()`関数
- `scripts/analysis/backtest_from_weights_with_stop.py`: `calculate_returns_from_weights()`関数
- `scripts/analysis/eval_stop_regimes.py`: `load_cross4_returns()`関数（`rebuild_port_ret_from_weights()`を使用）

## STOP条件の定義

STOP判定は以下の通りです：

```
alpha[t] = port_ret[t] - tpx_ret[t]

roll_alpha[t] = sum_{k=t-window}^{t-1} alpha[k]  (前日までの合計)
roll_tpx[t] = sum_{k=t-window}^{t-1} tpx_ret[k]  (前日までの合計)

stop_flag[t] = (roll_alpha[t] < 0) & (roll_tpx[t] < 0)
```

**重要**:
- `roll_alpha[t]`と`roll_tpx[t]`は`t-1`日までの情報を使用（`.shift(1)`）
- `stop_flag[t]`は`t`日のポートフォリオリターンに適用される

## STOP戦略の定義

### STOP0
- `stop_flag[t] = True`の場合: `port_ret[t] = 0.0`（100%キャッシュ）
- `stop_flag[t] = False`の場合: `port_ret[t] = sum_i w_i[t-1] * r_i[t]`（通常のcross4）

### Plan A
- `stop_flag[t] = True`の場合: `port_ret[t] = 0.75 * port_ret_cross4[t] + 0.25 * inv_ret[t]`
- `stop_flag[t] = False`の場合: `port_ret[t] = port_ret_cross4[t]`

### Plan B
- `stop_flag[t] = True`の場合: `port_ret[t] = 0.5 * port_ret_cross4[t]`（残り50%はキャッシュ）
- `stop_flag[t] = False`の場合: `port_ret[t] = port_ret_cross4[t]`

## 実装の統一

すべての実装はこの定義に従う必要があります：

1. **eval_stop_regimes.py**: この定義に従ってリターンを計算
2. **backtest_from_weights_with_stop.py**: この定義に従ってリターンを計算
3. **比較スクリプト**: 両者の結果が一致することを確認（`max_abs_diff < 1e-8`）

