# executor: stg終了ゲート（合格条件）

## 実行方法

```bash
python scripts/ops/run_executor_dryrun.py
```

## 生成物

### 1. RunLog

`executor_runs/runs/run_{run_id}.json`

必須フィールド:
- `run_id`: 実行ID
- `created_at`: 実行時刻（ISO形式）
- `mode`: "DRYRUN_PRE_SUBMIT"
- `latest_date`: 最新日
- `inputs_hash`: core成果物のhash（再現性確保）
- `intent_hash`: order_intentsのhash（冪等性確認用）
- `order_intents[]`: OrderIntentのリスト
  - `order_key`: 冪等性確保のためのkey
  - `symbol`, `side`, `qty`, `notional`, `price_ref`, `reason`
- `hedge_intents[]`: HedgeIntentのリスト
- `snapshots`: 事前チェック結果
  - `precheck_results[]`: 全チェック結果
  - `trading_day_check`: 休日チェック結果
  - `price_freshness`: 価格鮮度チェック結果
  - `cash_check`: 現物余力チェック結果
  - `margin_check`: CFD証拠金チェック結果
  - `connectivity_check`: 通信チェック結果
- `results`:
  - `precheck_passed`: bool
  - `stop_reason`: "STOP_BEFORE_SUBMIT"等
  - `password_entered`: bool（パスワード入力した事実のみ、パスワード自体は保存しない）
  - `ui_reflected`: bool
  - `ui_reflection_details`: UI反映詳細
  - `errors[]`: エラー情報

### 2. OrderIntent CSV（任意だが推奨）

`executor_runs/intents/order_intent_{run_id}.csv`

監査・差分比較用

## 合格条件

### 1. 冪等性（最重要）

同一`latest_date`で2回実行して：

- `intent_hash`が完全一致
- `order_intents`の`order_key`が完全一致

確認方法:
```bash
# 1回目実行
python scripts/ops/run_executor_dryrun.py

# 2回目実行（同一latest_date）
python scripts/ops/run_executor_dryrun.py

# intent_hashを比較
# executor_runs/runs/run_*.json から intent_hash を抽出して比較
```

### 2. フェイルセーフ

#### 休日
- `trading_day_check.is_trading_day = false`
- `order_intents`が空 or 全SKIP
- `stop_reason`に理由が記録

#### 価格stale
- `price_freshness`にstale情報が記録
- config通り`HALT`/`SKIP`/`USE_LAST`が実行
- `stop_reason`または`errors`に理由が記録

#### 余力不足
- `cash_check`または`margin_check`に不足情報が記録
- 縮小 or SKIPが実行
- 縮小率・結果が`snapshots`に記録

#### 通信/UNKNOWN
- `connectivity_check`に結果が記録
- cooldownルールが効く（SKIP/HALT）
- `stop_reason`に理由が記録

## Exit Code

- `0`: 成功（PRE_SUBMITで正常停止）
- `2`: HALT（事前チェック失敗等）
- `1`: 例外

## 判定手順

1. **単体実行**: `python scripts/ops/run_executor_dryrun.py`
2. **RunLog確認**: `executor_runs/runs/run_*.json`が生成されているか
3. **冪等性確認**: 同一latest_dateで2回実行して`intent_hash`一致を確認
4. **フェイルセーフ確認**: 各種エッジケースで適切に停止することを確認

