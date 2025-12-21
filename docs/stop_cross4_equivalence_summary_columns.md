# stop_cross4_equivalence_summary.csv カラム説明

## 概要

`stop_cross4_equivalence_summary.csv` は、STOP付cross4のweights版（weights→returns）とeval_stop_regimes.py版（return合成）の差分検証結果をまとめたサマリーファイルです。

## カラム一覧と説明

### 1. `strategy` (文字列)
- **意味**: 戦略名
- **値**: `baseline`, `stop0`, `planA`, `planB` のいずれか
- **説明**: 
  - `baseline`: STOP無しのcross4（ベースライン）
  - `stop0`: STOP期間中は全銘柄weight=0（100% cash）
  - `planA`: STOP期間中はcross4 75% + インバースETF 25%
  - `planB`: STOP期間中はcross4 50%（残り50%はcash）

### 2. `window` (文字列)
- **意味**: ウィンドウサイズ
- **値**: `baseline`, `w60`, `w120` のいずれか
- **説明**: 
  - `baseline`: baseline戦略ではwindowは適用されない
  - `w60`: 60日間のrolling windowでSTOP条件を計算
  - `w120`: 120日間のrolling windowでSTOP条件を計算

### 3. `status` (文字列)
- **意味**: 一致判定のステータス
- **値**: `PASS` または `FAIL`
- **説明**: 
  - `PASS`: 全日のリターン差分が許容誤差（1e-8）以内で一致
  - `FAIL`: 1日以上で許容誤差を超える差分が存在
- **判定基準**: `abs(port_ret_cc_weights - port_ret_cc_eval) <= 1e-8` が全日に成立するか

### 4. `common_dates` (整数)
- **意味**: 比較対象となった共通日数
- **単位**: 日
- **説明**: weights版とeval版の両方に存在する日付の数。この日数分だけ比較が行われています。

### 5. `mean_abs_diff` (浮動小数点数)
- **意味**: 日次リターン差分の平均絶対値
- **単位**: 無次元（リターンと同じ単位）
- **計算式**: `mean(abs(port_ret_cc_weights - port_ret_cc_eval))`
- **説明**: 1日あたりの平均的な差分の大きさ。値が小さいほど一致度が高い。

### 6. `max_abs_diff` (浮動小数点数)
- **意味**: 日次リターン差分の最大絶対値
- **単位**: 無次元（リターンと同じ単位）
- **計算式**: `max(abs(port_ret_cc_weights - port_ret_cc_eval))`
- **説明**: 全期間で最も大きかった差分。異常な日や特定の問題点を特定するのに有用。

### 7. `cum_ret_weights` (浮動小数点数)
- **意味**: weights版の累積リターン（倍率 - 1.0）
- **単位**: 無次元（例: 1.76 = 176%の累積リターン）
- **計算式**: `(1.0 + port_ret_cc_weights).prod() - 1.0`
- **説明**: weightsから計算したリターンを合成した累積リターン。期間全体でのパフォーマンスを表す。

### 8. `cum_ret_eval` (浮動小数点数)
- **意味**: eval版の累積リターン（倍率 - 1.0）
- **単位**: 無次元（例: 2.47 = 247%の累積リターン）
- **計算式**: `(1.0 + port_ret_cc_eval).prod() - 1.0`
- **説明**: eval_stop_regimes.pyでreturn合成方式で計算した累積リターン。比較の基準となる値。

### 9. `cum_ret_diff` (浮動小数点数)
- **意味**: 累積リターンの差分
- **単位**: 無次元
- **計算式**: `cum_ret_weights - cum_ret_eval`
- **説明**: 
  - 正の値: weights版の方が累積リターンが大きい
  - 負の値: eval版の方が累積リターンが大きい（通常はこちら）
  - 絶対値が大きいほど、累積的な差分が大きいことを示す

## 解釈のポイント

### status が FAIL の場合

1. **mean_abs_diff を確認**
   - 0.01未満（1%未満）: 日次レベルでは比較的近い
   - 0.01以上: 日次レベルで有意な差分がある

2. **max_abs_diff を確認**
   - 特定の日に大きな差分が発生していないか確認
   - 0.1以上（10%以上）の場合は、特定の日の異常を調査する必要がある

3. **cum_ret_diff を確認**
   - 日次差分は小さいが累積差分が大きい場合、日付アライメントや複利効果の影響が考えられる
   - 絶対値が0.1以上（10%以上）の場合は、累積的な問題がある可能性がある

### 典型的な不一致の原因

- **STOP判定系列の不一致**: STOP日数が異なる（例: eval側286日 vs weights側203日）
- **インバースETF扱いの違い**: PlanAでのインバースETF（1569.T）のweight設定が異なる
- **日付アライメント**: weights[t]でreturns[t+1]を計算する際の日付ずれ
- **リターン計算方法の違い**: 複利計算や欠損値処理の違い

## 例: 実際のデータ解釈

```
strategy,window,status,common_dates,mean_abs_diff,max_abs_diff,cum_ret_weights,cum_ret_eval,cum_ret_diff
planA,w60,FAIL,2410,0.011553448,0.230560846,2.260587616,4.649153474,-2.388565858
```

この例では：
- **status**: FAIL（一致していない）
- **mean_abs_diff**: 0.0116（約1.16%）- 日次差分は比較的小さい
- **max_abs_diff**: 0.2306（約23%）- 特定の日に大きな差分が発生
- **cum_ret_diff**: -2.39（約-239%）- 累積リターンで大きな差（eval版の方が大幅に高い）
- **解釈**: 日次レベルでは近いが、累積で大きく乖離。STOP判定やインバースETF扱いの違いが影響している可能性が高い。

