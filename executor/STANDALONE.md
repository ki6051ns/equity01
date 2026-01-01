# executor: 単体稼働確認

## 依存関係チェック

### executor/内のexecution/依存

```bash
# executor/内でexecution/を参照していないことを確認
rg "from execution|import execution" executor -n
# → No matches（依存なし）

rg "execution/" executor -n
# → コメント・ドキュメント内のみ（コード依存なし）
```

### scripts/からのexecutor呼び出し

```bash
# scripts/がexecutorを呼ぶ際にexecution/を経由していないことを確認
rg "from executor|import executor" scripts -n
# → 現在はなし（executor単体で実行）
```

## 単体実行（最小ハッピーパス）

### 前提条件

- core成果物: `data/processed/daily_portfolio_guarded.parquet` が存在
- calendar正本: `data/processed/index_tpx_daily.parquet` が存在

### 実行方法

```bash
# executor単体で実行
python -m executor.dryrun

# または
python executor/dryrun.py
```

### 期待される成果物

1. **`executor_runs/runs/run_{run_id}.json`** が生成される
2. RunLogに以下が含まれる：
   - `latest_date`: 最新日
   - `mode`: "DRYRUN_PRE_SUBMIT"
   - `order_intents`: OrderIntentのリスト
   - `hedge_intents`: HedgeIntentのリスト
   - `snapshots`: 事前チェック結果
   - `results.stop_reason`: "STOP_BEFORE_SUBMIT"

3. **冪等性**: 同一latest_dateで再実行してもintentが不変

## stg終了ゲート

- ✅ mode=DRYRUN_PRE_SUBMIT
- ✅ ログイン成功（スタブ実装）
- ✅ パスワード入力済み（事実のみ記録、パスワード自体は保存しない）
- ✅ 発注確定クリック直前で停止
- ✅ RunLogに以下が記録される：
  - 注文一覧（symbol/side/qty/price_ref）
  - 余力/証拠金スナップショット
  - 停止理由: STOP_BEFORE_SUBMIT

