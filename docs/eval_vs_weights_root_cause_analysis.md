# eval_stop_regimes系とweights型バックテストの乖離分析

## 概要

`eval_stop_regimes.py`（eval側）と`backtest_from_weights_with_stop.py`（weights側）のポートフォリオリターン計算結果の乖離について、原因を特定・分類するための分析フレームワーク。

## 原因分類

差分が発生する原因は以下の4つに分類される：

1. **date_alignment（日付アライン）**: `w[t-1] * r[t]` vs `w[t] * r[t]` の違い
2. **stop_flag_mismatch（STOPフラグ不一致）**: STOP条件の判定タイミングや系列の違い
3. **missing_fill（欠損値処理）**: NaN/欠損値の埋め方（0埋め vs drop）の違い
4. **price_diff（価格系列差）**: `adj_close` vs `close` の違い

## 分析ツール

### 1. debug_eval_vs_weights_day.py

特定日について、詳細な差分分析を実行。

```bash
python scripts/analysis/debug_eval_vs_weights_day.py --strategy stop0 --window 60 --date 2024-08-05
```

**出力内容**:
- 【1】日付アラインの完全可視化
  - `target_trade_date`: 対象日（t）
  - `w_used_date`: 実際に使用したweightsのdate
  - `ret_date`: リターン計算に使ったdate
  - `式表記`: w[?] * r[?] の形式で表示
- 【3】価格系列差の寄与切り分け
  - `adj_close`版と`close`版の差分定量化
  - Top10 |Δcontrib| 銘柄
- 【STEP 5】原因ラベル特定
  - 寄与ベースの自動分類結果

### 2. debug_single_date_reproduction.py

差分が最大の日について、3つのパターンを並べて比較：

- `w[t-1] * r[t]`（標準）
- `w[t] * r[t]`（look-aheadの可能性）
- `w[t-1] * r[t+1]`（念のため）

```bash
python scripts/analysis/debug_single_date_reproduction.py --strategy stop0 --window 60 --date 2024-08-05
```

eval側の値と一致するパターンを特定することで、「evalがどの時間軸のロジックか」を確定する。

## 正しい定義（weights側を正とする）

### ポートフォリオリターン計算

```python
# 定義（docs/return_definition.md参照）
r_i[t] = adj_close_i[t] / adj_close_i[t-1] - 1
port_ret[t] = sum_i w_i[t-1] * r_i[t]
```

**重要**: `w[t-1] * r[t]` が正しい定義。`w[t] * r[t]`はlook-aheadバイアスを含むため使用しない。

### STOP条件

```python
alpha = port_ret - tpx_ret
roll_alpha = alpha.rolling(window=w, min_periods=1).sum().shift(1)
roll_tpx = tpx_ret.rolling(window=w, min_periods=1).sum().shift(1)
stop_flag = (roll_alpha < 0) & (roll_tpx < 0)
```

## 原因特定の手順

1. **日付アラインの確認**
   - `debug_eval_vs_weights_day.py`の【1】日付アライン情報を確認
   - eval側とweights側の`w_used_date`と`ret_date`を比較
   - 式表記が一致しているか確認

2. **パターンマッチング**
   - `debug_single_date_reproduction.py`で3パターンをテスト
   - eval側のport_retと最も一致するパターンを特定

3. **価格系列差の定量化**
   - `debug_eval_vs_weights_day.py`の【3】価格系列差の寄与切り分けを確認
   - `adj_close`と`close`の差分が大きい場合は原因④

4. **原因ラベルの確認**
   - 【STEP 5】原因ラベル特定の結果を確認
   - `cause:1:date_alignment`など、分類結果を参照

## 意思決定基準

### 原因①（date_alignment）が確定した場合

**結論**: eval側は旧ロジック由来（`w[t] * r[t]`を使用している可能性）であり、**weights側（`w[t-1] * r[t]`）を正とする**。

**対応**:
- eval側のコードをweights側の定義に合わせて修正
- または、eval側をdeprecatedとして明記し、weights側を使用する

### 原因④（price_diff）が副因の場合

- `adj_close`と`close`の差分が大きい（`abs_diff(port_ret) > 1e-6`）場合、価格系列の選択も影響している
- 日付アラインと併せて修正が必要

### 複合原因の場合

- 複数の原因が同時に影響している可能性がある
- `unknown_multifactorial`として分類される
- 各原因を順次修正していく

## 実装ファイル

- `scripts/analysis/debug_eval_vs_weights_day.py`: 詳細差分分析
- `scripts/analysis/debug_single_date_reproduction.py`: 単日再現テスト
- `scripts/analysis/rebuild_port_ret_from_weights.py`: 寄与計算の共通関数
- `docs/return_definition.md`: リターン計算の定義

## 関連ドキュメント

- [return_definition.md](return_definition.md): ポートフォリオリターンとSTOP条件の定義
- [eval_stop_regimes_return_analysis.md](eval_stop_regimes_return_analysis.md): eval側のリターン分析

