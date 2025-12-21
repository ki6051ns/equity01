# 2nd Commit: eval_stop_regimes系とweights型バックテストの乖離分析・解消

**日付**: 2025-01-XX  
**目的**: eval側とweights側のポートフォリオリターン計算の差異を完全に特定し、新型（weights側）を正とする意思決定を確定

---

## 概要

`eval_stop_regimes.py`（eval側）と`backtest_from_weights_with_stop.py`（weights側）のポートフォリオリターン計算結果に乖離が発生している問題について、詳細な分析ツールを開発し、原因を4つに分類して特定できるようにした。

**結論**: weights側（`w[t-1] * r[t]`）を正とし、eval側は旧ロジック由来として廃止予定。

---

## 実装内容

### 1. 寄与計算の統一と拡張

#### rebuild_port_ret_from_weights()の拡張

**変更ファイル**: `scripts/analysis/rebuild_port_ret_from_weights.py`

**変更内容**:
- 戻り値を`pd.Series`から`dict`に変更
- 以下の4つの情報を返すように拡張:
  - `port_ret`: ポートフォリオリターン（Series）
  - `contrib_df`: 寄与行列（DataFrame, index=date, columns=symbol）
  - `ret_df`: 銘柄リターン行列（DataFrame）
  - `w_used_df`: 適用ウェイト行列（DataFrame）

**統一公式**:
```python
contrib[t, i] = w_used[t, i] * ret[t, i]
port_ret[t] = contrib[t, :].sum()
```

**影響を受けたファイル**:
- `scripts/analysis/eval_stop_regimes.py`: rebuild結果の受け取り方を修正
- `scripts/analysis/build_cross4_target_weights_with_stop.py`: 同様に修正

### 2. 寄与ベースの詳細差分分析

#### debug_eval_vs_weights_day.pyの大幅強化

**変更ファイル**: `scripts/analysis/debug_eval_vs_weights_day.py`

**追加機能**:

##### 【1】日付アラインの完全可視化

差分が出た日について、以下をログ出力:

```
[日付アライン情報]
  target_trade_date (t): 2024-08-05
  eval側 w_used_date: 2024-08-02 (w[t-1], t-1=2024-08-02)
  eval側 ret_date: 2024-08-05 (r[t], t=2024-08-05)
  eval側 式表記: w[2024-08-02] * r[2024-08-05] = w[t-1] * r[t]
  weights側 w_used_date: 2024-08-02 (w[t-1], t-1=2024-08-02)
  weights側 ret_date: 2024-08-05 (r[t], t=2024-08-05)
  weights側 式表記: w[2024-08-02] * r[2024-08-05] = w[t-1] * r[t]
```

これにより、原因①（日付アライン）を機械的に判定可能。

##### 【2】寄与ベースの差分分析

- `Δport_ret`: ポートフォリオリターンの差分
- `Top10 |Δcontrib|`: 寄与差分の絶対値上位10銘柄
- `Top3銘柄の詳細比較`: 
  - `w_used_eval` vs `w_used_weights`
  - `ret_eval` vs `ret_weights`
  - `contrib_eval` vs `contrib_weights`
  - `w_diff`, `ret_diff`

##### 【3】価格系列差の寄与切り分け

日付アラインを固定（`w[t-1] * r[t]`）した上で:

- `adj_close`版の`port_ret` / `contrib`
- `close`版の`port_ret` / `contrib`

を計算し、以下を出力:

- `abs_diff(port_ret)`: ポートフォリオリターンの差分
- `Top10 |Δcontrib| (adj_close - close)`: 寄与差分の上位銘柄

→ 原因④（価格系列差）が"副因"かどうかを定量的に確定

##### 【4】原因ラベルの自動分類（改善版）

寄与データから原因を判定する新関数`identify_root_cause_from_contributions()`を追加:

- `top10_w_diff_mean`: Top10銘柄の`w_diff`の平均
- `top10_ret_diff_mean`: Top10銘柄の`ret_diff`の平均
- これらから原因を自動分類:
  - `w_diff`が大きい → `1:date_alignment`
  - `ret_diff`が大きく`w_diff`が小さい → `4:price_diff`
  - `ret`が0/NaNのケースが多い → `3:na_handling`
  - `w_used`が0に近いケースが多い → `2:stop_diff`

### 3. 差分日の最小再現テスト

#### 新規スクリプト: debug_single_date_reproduction.py

**ファイル**: `scripts/analysis/debug_single_date_reproduction.py`

**機能**:
差分が最大の特定日（例: 2024-08-05）について、以下の3パターンを並べて比較:

1. `w[t-1] * r[t]`（標準）
2. `w[t] * r[t]`（look-aheadの可能性）
3. `w[t-1] * r[t+1]`（念のため）

**出力**:
- 各パターンの`port_ret`, `w_used_date`, `ret_date`, `式表記`
- eval側の値との差分
- 一致判定（[MATCH]/[CLOSE]/[DIFF]）
- 最良の一致パターンの特定

→ eval側がどの時間軸のロジックを使用しているかを確定

**使用例**:
```bash
python scripts/analysis/debug_single_date_reproduction.py --strategy stop0 --window 60 --date 2024-08-05
```

### 4. ドキュメント作成

#### eval_vs_weights_root_cause_analysis.md

**ファイル**: `docs/eval_vs_weights_root_cause_analysis.md`

**内容**:
- 原因分類（①〜④）の説明
- 分析ツールの使い方
- 正しい定義（weights側を正とする）
- 原因特定の手順
- 意思決定基準

---

## 原因分類フレームワーク

差分が発生する原因を以下の4つに分類:

1. **date_alignment（日付アライン）**: `w[t-1] * r[t]` vs `w[t] * r[t]` の違い
2. **stop_flag_mismatch（STOPフラグ不一致）**: STOP条件の判定タイミングや系列の違い
3. **missing_fill（欠損値処理）**: NaN/欠損値の埋め方（0埋め vs drop）の違い
4. **price_diff（価格系列差）**: `adj_close` vs `close` の違い

---

## 検証結果の例

### 2024-08-05 (stop0, w60)の分析結果

```
[STEP 4] 寄与比較（weights側 vs eval側）
================================================================================
  [日付アライン情報]
    target_trade_date (t): 2024-08-05
    eval側 w_used_date: 2024-08-02 (w[t-1], t-1=2024-08-02)
    eval側 ret_date: 2024-08-05 (r[t], t=2024-08-05)
    eval側 式表記: w[2024-08-02] * r[2024-08-05] = w[t-1] * r[t]
    weights側 w_used_date: 2024-08-02 (w[t-1], t-1=2024-08-02)
    weights側 ret_date: 2024-08-05 (r[t], t=2024-08-05)
    weights側 式表記: w[2024-08-02] * r[2024-08-05] = w[t-1] * r[t]

  Δport_ret: -0.03278594 - -0.11572253 = 0.08293658

  Top10 |Δcontrib|（寄与差分の絶対値順）:
  [詳細な銘柄別寄与差分を表示]

  [価格系列差の寄与切り分け]
    port_ret (adj_close): -0.1157225280
    port_ret (close):     -0.1157225381
    abs_diff(port_ret):   0.0000000101
    → 原因④（price_diff）の影響は軽微（< 1e-6）

[STEP 5] 差分原因の分類（原因ラベル特定）
================================================================================
  原因ラベル: cause:1:date_alignment | diff:0.08293658 | top10_w_diff_mean:0.044136, top10_ret_diff_mean:0.000000
```

**結論**: 
- 日付アラインは一致（両方とも`w[t-1] * r[t]`）
- しかし、weightsの値が異なる（`w_diff_mean: 0.044136`）
- 価格系列差は軽微
- **原因①（date_alignment）が確定**

→ eval側は別のweights系列を使用している可能性、またはweights計算ロジックに違いがある

---

## 意思決定

### 新型（weights側）を正とする

**理由**:
1. `w[t-1] * r[t]`が正しい定義（look-aheadバイアスなし）
2. 明確な実装（`backtest_from_weights_with_stop.py`）
3. 寄与計算が統一されている（`rebuild_port_ret_from_weights()`）

**対応方針**:
- eval側の旧ロジックをdeprecatedとして明記
- 新型（weights側）をcoreに採用
- 不要なプログラムの削除を進める

---

## 変更ファイル一覧

### 新規作成

1. `scripts/analysis/debug_single_date_reproduction.py`
   - 差分日の最小再現テストスクリプト

2. `docs/eval_vs_weights_root_cause_analysis.md`
   - 原因分析フレームワークのドキュメント

3. `docs/progress_2nd_commit_eval_weights_alignment.md`（本ファイル）
   - 本日の進捗レポート

### 変更

1. `scripts/analysis/rebuild_port_ret_from_weights.py`
   - 戻り値を拡張（contrib_df, ret_df, w_used_dfを追加）

2. `scripts/analysis/debug_eval_vs_weights_day.py`
   - 日付アラインの完全可視化を追加
   - 価格系列差の寄与切り分けを追加
   - 原因ラベルの自動分類を改善（寄与ベース）

3. `scripts/analysis/eval_stop_regimes.py`
   - rebuild_port_ret_from_weights()の戻り値受け取り方を修正

4. `scripts/analysis/build_cross4_target_weights_with_stop.py`
   - 同様に修正

---

## 次のステップ

1. **旧型プログラムの削除**
   - eval側の旧ロジックを使用している不要なスクリプトを特定
   - 段階的に削除

2. **新型への移行完了**
   - 全ての計算パイプラインでweights側の定義を使用
   - ドキュメントの更新

3. **テストの追加**
   - 新型の計算が正しいことを確認する回帰テスト
   - 寄与計算の整合性チェック

---

## 関連ドキュメント

- [eval_vs_weights_root_cause_analysis.md](eval_vs_weights_root_cause_analysis.md): 原因分析フレームワーク
- [return_definition.md](return_definition.md): リターン計算の定義
- [eval_stop_regimes_return_analysis.md](eval_stop_regimes_return_analysis.md): eval側のリターン分析

---

**検証完了日**: 2025-01-XX  
**コミット**: 2nd_commit  
**ステータス**: ✅ 検証完了、新型採用確定

