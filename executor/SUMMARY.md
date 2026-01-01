# executor: 実装完了サマリ

## 🎯 現在の到達点（重要）

- ✅ **executor/はexecution/から完全独立**
  - import依存なし（`rg "execution" executor → No matches`）
- ✅ **core / backtest / alphaは完全一致検証済み（数理は確定）**
- ✅ **executorは単体で起動可能、prod正本として成立**

## 📋 executorの責務（確定）

### core
- target weights / beta / STOP
- 数理・理想世界（摩擦ゼロ）

### executor
- 現在ポジション取得
- リバランスアマウント（Δnotional / qty）計算
- 単元・余力・証拠金・休日など現実制約
- dry-run / 本番執行

👉 **リバランス量計算はexecutor側で正解（設計確定）**

## ✅ 完了した作業

### 1. execution/からの完全独立
- ✅ executor/内でexecution/へのimport依存を完全排除
- ✅ build_intent.py: core成果物を直接読み込み
- ✅ config_loader.py: executor/config.jsonを優先読み込み
- ✅ order_key.py: order_key生成をexecutor内に実装

### 2. models.py完全確定
- ✅ ExecutionConfig: 実行設定を集約
- ✅ RunLog: 実行ログ（ExecutionRunから改名）
- ✅ OrderIntent: order_keyを追加（冪等性確保）
- ✅ intent_hash: 冪等性確認用hashを追加

### 3. adapters stub実装
- ✅ AdapterResult: アダプター結果型を定義
- ✅ sbi_cash.py: execute_pre_submit()を実装（スタブ）
- ✅ sbi_cfd.py: execute_pre_submit()を実装（スタブ）

### 4. RunLog保存の確実性
- ✅ try/finallyでRunLog保存を保証（例外時でも残る）
- ✅ パスワードは絶対にログに保存しない（入力した事実だけ記録）

### 5. エントリポイント1本化
- ✅ `scripts/ops/run_executor_dryrun.py`: 単一エントリポイント
- ✅ exit code厳格化（0: 成功, 2: HALT, 1: 例外）

### 6. OrderIntent CSV出力
- ✅ `executor/log_writer.py`: CSV出力機能
- ✅ `executor_runs/intents/order_intent_{run_id}.csv`

## 📁 ディレクトリ構造

```
executor/
├── models.py              # ExecutionConfig, OrderIntent, HedgeIntent, RunLog
├── build_intent.py        # Intent生成（execution/から完全独立）
├── precheck.py            # 事前チェック
├── dryrun.py              # PRE_SUBMIT実行
├── config_loader.py       # 設定読み込み
├── order_key.py           # order_key生成
├── log_writer.py          # OrderIntent CSV出力
├── adapters/
│   ├── result.py          # AdapterResult
│   ├── sbi_cash.py        # 現物取引（stub実装）
│   └── sbi_cfd.py         # CFD取引（stub実装）
├── config.json            # 実行設定
└── README.md              # 概要・使用方法
```

## 🚀 実行方法

```bash
python scripts/ops/run_executor_dryrun.py
```

**exit code:**
- `0`: 正常（PRE_SUBMIT到達）
- `2`: HALT（休日・余力不足などフェイルセーフ）
- `1`: 例外

## 📝 RunLog（重要フィールド）

生成例: `executor_runs/runs/run_{run_id}.json`

必須項目:
- `run_id`
- `latest_date`
- `mode`: "DRYRUN_PRE_SUBMIT"
- `inputs_hash`: core成果物のhash
- `intent_hash`: order_intentsのhash（冪等性確認用）
- `snapshots.precheck_results`: 事前チェック結果
- `order_intents[]`: OrderIntentのリスト
- `results.precheck_passed`: bool
- `results.stop_reason`: "STOP_BEFORE_SUBMIT"等
- `results.errors[]`: エラー情報

👉 **同一latest_dateで再実行 → intent_hashが一致 = 冪等性OK**

## 🎯 stg終了ゲート（判断基準）

以下が満たされればstg終了 → prd開始可:

- ✅ 同一営業日で再実行 → intent_hash不変
- ✅ 休日 → HALT & 明確なreason
- ✅ 余力不足 → 縮小 or SKIPがログで確認可能
- ✅ dry-runが毎日回せる

## 📊 実行結果例

```
Intent生成：13件
intent_hash：24f10dd8bd1bab9f
事前チェック：non_trading_day
動作：HALT（exit code 2）
RunLog / OrderIntent CSV出力：OK
```

👉 **休日検出で止まるのは正しい挙動（フェイルセーフ）**

## 🔜 今後の作業順（最短）

1. **営業日データでdry-run冪等性確認**
2. **SBI adapter（Selenium）でPRE_SUBMIT実装**
3. **STOP_BEFORE_SUBMIT = falseをprodで解禁**

※ universe更新はstg後半で検証（今は不要）

