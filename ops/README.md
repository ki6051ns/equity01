# ops: executor dry-run実行スクリプト

## run_executor_dryrun.ps1

executor dry-runを実行するPowerShellスクリプト。

### Exit Code

- `0`: 成功（PRE_SUBMIT到達）
- `2`: HALT（事前チェック失敗：休日・価格stale・余力不足など）
- `1`: 例外（想定外エラー）

### 重要：Exit Code 2について

**Exit Code 2は「失敗」ではなく「正常な停止」です。**

- 休日検出 → exit code 2（正常：取引できないので停止）
- 価格stale → exit code 2（正常：安全のため停止）
- 余力不足 → exit code 2（正常：安全のため停止）

タスクスケジューラで実行する場合：
- **Exit Code 2も正常終了として扱うことを推奨**
- タスクスケジューラの「戻り値が0以外の場合は失敗」という設定を無効化
- または、ラッパースクリプトでexit code 2を0に変換

### 使い方

```powershell
# 基本実行
powershell -ExecutionPolicy Bypass -File .\ops\run_executor_dryrun.ps1

# タイムスタンプなし（latest.log）
powershell -ExecutionPolicy Bypass -File .\ops\run_executor_dryrun.ps1 -NoTimestamp
```

### ログファイル

- `executor_runs/logs/run_executor_dryrun_YYYYMMDD_HHMMSS.log`
- `executor_runs/logs/run_executor_dryrun_latest.log`（-NoTimestamp指定時）

### タスクスケジューラ設定例

**基本設定:**
- プログラム: `powershell.exe`
- 引数: `-ExecutionPolicy Bypass -NoProfile -File "C:\path\to\equity01\ops\run_executor_dryrun.ps1"`
- 開始ディレクトリ: `C:\path\to\equity01`

**重要:**
- 「タスクが正常に完了したと見なす場合の終了コード」を設定
- 0, 2 を正常終了として扱う（設定できない場合は、ラッパースクリプトを使用）

