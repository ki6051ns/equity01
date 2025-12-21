# eval_stop_regimes.py Return使用箇所の分析

## 現状の確認

### 1. STOP判定ブロック (`compute_stop_conditions`)

```python
# 行308-324
alpha = port_ret - tpx_ret

for window in windows:
    # ✅ ルックアヘッドバイアス回避: 前日までの情報を使うため .shift(1)
    roll_alpha = alpha.rolling(window=window, min_periods=1).sum().shift(1)
    roll_tpx = tpx_ret.rolling(window=window, min_periods=1).sum().shift(1)
    
    stop_cond = (roll_alpha < 0) & (roll_tpx < 0)
```

**確認事項:**
- `port_ret`は`load_cross4_returns()`から取得（行207）
- `port_ret`は`horizon_ensemble_variant_cross4.parquet`の`port_ret_cc`列
- STOP判定は`.shift(1)`でt-1までの情報を使用（正しい）

### 2. 戦略return適用ブロック (`compute_strategy_returns`)

```python
# 行386: STOP0
ret_stop0 = np.where(stop_cond, 0.0, port_ret.values)

# 行416: Plan A
ret_A = np.where(stop_cond, 0.75 * port_ret.values + 0.25 * inv_ret_aligned.values, port_ret.values)

# 行464: Plan B
ret_B = np.where(stop_cond, 0.5 * port_ret.values, port_ret.values)
```

**確認事項:**
- すべて`port_ret.values`を使用
- `port_ret`は`load_cross4_returns()`から取得したもの
- `port_ret`が`ret_raw`か、何らかの変換（shift/rolling_sum）を経ているか不明

## 問題点

1. **`port_ret`の正体が不明確**
   - `horizon_ensemble_variant_cross4.parquet`の`port_ret_cc`がどのように計算されているか
   - すでにshiftやrolling_sumを経ている可能性

2. **判定用returnと適用用returnの整合性**
   - STOP判定では`port_ret`（元のreturn）を使用
   - 戦略適用でも同じ`port_ret`を使用
   - しかし、`port_ret`がすでに変換済みなら、日付のズレが発生する可能性

## 修正方針

### ゴール
- **判定は t の情報まで**: 既に`.shift(1)`で実現済み ✅
- **適用は必ず t+1**: `stop_cond[t]`は`t-1`までの情報で判定したものなので、`ret_raw[t]`に適用される ✅
- **port_ret に足すのは常に ret_raw[t]**: 確認が必要 ❓

### 確認すべきこと

1. `load_cross4_returns()`が返す`port_ret`が`ret_raw`（生の日次リターン）であることを確認
2. `horizon_ensemble_variant_cross4.parquet`の`port_ret_cc`がどのように計算されているかを確認
3. もし変換済みなら、生のreturnを別途読み込むか、変換を解除する

## 次のステップ

1. `horizon_ensemble_variant_cross4.parquet`の生成元を確認
2. `port_ret_cc`が`ret_raw`かどうかを確認
3. 必要に応じて、`load_cross4_returns()`で`ret_raw`を明示的に取得

