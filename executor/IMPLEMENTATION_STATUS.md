# executor: 実装状況

## ✅ 完了

### 1. execution/からの完全独立
- ✅ executor/内でexecution/へのimport依存ゼロ
- ✅ build_intent.py: core成果物を直接読み込み
- ✅ config_loader.py: executor/config.jsonを優先

### 2. エントリポイント1本化
- ✅ `scripts/ops/run_executor_dryrun.py`: 単一エントリポイント
- ✅ exit code厳格化（0: 成功, 2: HALT, 1: 例外）

### 3. RunLog完全化
- ✅ intent_hash追加（冪等性確認用）
- ✅ snapshotsに事前チェック結果を詳細記録
- ✅ try/finallyでRunLog保存を保証

### 4. OrderIntent CSV出力
- ✅ `executor/log_writer.py`: CSV出力機能
- ✅ `executor_runs/intents/order_intent_{run_id}.csv`

### 5. adapters stub実装
- ✅ `executor/adapters/result.py`: AdapterResult型
- ✅ `sbi_cash.py`: execute_pre_submit()実装
- ✅ `sbi_cfd.py`: execute_pre_submit()実装

## 📋 実行方法

```bash
python scripts/ops/run_executor_dryrun.py
```

## 📁 生成物

1. `executor_runs/runs/run_{run_id}.json` - RunLog
2. `executor_runs/intents/order_intent_{run_id}.csv` - OrderIntent CSV

## 🎯 stg終了ゲート

詳細は `executor/STG_GATE.md` を参照

- ✅ 冪等性（intent_hash一致）
- ✅ フェイルセーフ（休日/価格stale/余力不足/通信）

