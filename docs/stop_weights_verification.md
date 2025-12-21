# STOP付weights整合性検証

## 目的

STOP付weights生成の再発防止のため、以下の3つの検証を自動実行します：

1. **構文チェック**: `build_cross4_target_weights_with_stop.py`の構文が正しいか確認
2. **weights再生成**: weightsファイルが正常に生成できるか確認
3. **PlanA weightsサニティチェック**: PlanA weightsが設計通りになっているか確認

## 検証項目

### CHECK 1: 構文チェック

```bash
python -m py_compile scripts/analysis/build_cross4_target_weights_with_stop.py
```

- 目的: IndentationErrorなどの構文エラーを検出
- 合格条件: エラーなくコンパイルできること

### CHECK 2: weights再生成

```bash
python scripts/analysis/build_cross4_target_weights_with_stop.py
```

- 目的: weightsファイルが正常に生成できるか確認
- 合格条件: スクリプトが最後まで完走し、全weightsファイルが保存されること

### CHECK 3: PlanA weightsサニティチェック

PlanA weights (`cross4_target_weights_planA_w60.parquet`) の内容を検証します。

#### 検証項目

1. **inv>0日数 == STOP日数**
   - インバースETF（1569.T）のweight > 0の日数が、STOP日数と一致することを確認
   - PlanAでは「STOP日のみinv=0.25、非STOP日はinv=0.0」であるべき

2. **1356.T > 0 日数 == 0**
   - 禁止ティッカー（1356.T）にweightが入っていないことを確認
   - PlanAでは1569.T以外のインバース系を禁止

3. **STOP日の平均 (inv/non_inv/total) ≈ (0.25/0.75/1.0)**
   - STOP日のインバースETF weight平均が約0.25
   - STOP日の非インバースweight合計平均が約0.75
   - STOP日の合計weight平均が約1.0

## 実行方法

### 全検証を実行

```bash
python scripts/analysis/verify_stop_weights_integrity.py
```

### 個別にスキップ

```bash
# 構文チェックのみスキップ
python scripts/analysis/verify_stop_weights_integrity.py --skip-syntax

# weights再生成のみスキップ
python scripts/analysis/verify_stop_weights_integrity.py --skip-generation

# サニティチェックのみスキップ
python scripts/analysis/verify_stop_weights_integrity.py --skip-sanity
```

## CI/ローカルチェックへの組み込み

### 推奨チェックフロー

```bash
# 1. 構文チェック
python -m py_compile scripts/analysis/build_cross4_target_weights_with_stop.py

# 2. weights再生成
python scripts/analysis/build_cross4_target_weights_with_stop.py

# 3. サニティチェック（統合スクリプトを使用）
python scripts/analysis/verify_stop_weights_integrity.py --skip-generation

# または、個別に確認
python scripts/analysis/check_stop_weights_inverse.py --strategy planA --window 60
```

### 合格条件

以下の3点が全て満たされること：

1. ✅ 構文チェック: エラーなし
2. ✅ weights再生成: 最後まで完走
3. ✅ PlanAサニティチェック:
   - inv>0日数 == STOP日数
   - 1356.T > 0 日数 == 0
   - STOP日の inv 平均 ≈ 0.25, non_inv ≈ 0.75, total ≈ 1.0

## 過去の不具合と再発防止

### 過去の不具合例

1. **IndentationError (line 352)**
   - 原因: `else:`ブロック内のコードがインデントされていなかった
   - 影響: weights再生成ができず、古いparquetが残り続けた
   - 再発防止: 構文チェックで検出可能

2. **PlanA weightsが設計通りでない**
   - 原因: 非STOP日にもinv weightが残っていた、1356.Tが混入していた
   - 影響: STOPロジックが正しく機能しない
   - 再発防止: サニティチェックで検出可能

3. **STOP計算エラーを握りつぶす**
   - 原因: 例外をcatchして続行していた
   - 影響: STOPが効いていない状態でbacktestが進む
   - 再発防止: backtest側でエラー時に停止するように修正済み

## 関連ファイル

- `scripts/analysis/build_cross4_target_weights_with_stop.py`: weights生成スクリプト
- `scripts/analysis/check_stop_weights_inverse.py`: インバースETF weight確認スクリプト
- `scripts/analysis/verify_stop_weights_integrity.py`: 統合検証スクリプト（本ファイル）

