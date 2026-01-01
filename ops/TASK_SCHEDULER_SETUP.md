# タスクスケジューラ設定ガイド

## executor dry-run実行スクリプト

### 使用するスクリプト

**タスクスケジューラでは `run_executor_dryrun_scheduler.ps1` を使用してください。**

このスクリプトは exit code 2（HALT）を 0（成功）に変換するため、タスクスケジューラで「成功」として扱われます。

### タスクスケジューラ設定

#### 基本設定

1. **全般タブ**
   - 名前: `executor dry-run`
   - 説明: `executor dry-run実行（PRE_SUBMIT）`
   - セキュリティオプション:
     - ✅ 「ユーザーがログオンしているかどうかにかかわらず実行する」
     - ✅ 「最高の権限で実行する」（必要に応じて）

2. **トリガータブ**
   - 実行頻度: 毎営業日（例：平日 8:00）

3. **操作タブ**
   - 操作: プログラムの開始
   - プログラム/スクリプト: 
     ```
     powershell.exe
     ```
   - 引数の追加:
     ```
     -ExecutionPolicy Bypass -NoProfile -File "C:\Users\sohta\equity01\ops\run_executor_dryrun_scheduler.ps1"
     ```
   - **重要**: フルパスを使用してください（相対パスは避ける）

4. **条件タブ**
   - ✅ 「コンピューターをAC電源で使用している場合のみタスクを開始する」を**オフ**（推奨）

5. **設定タブ**
   - ✅ 「タスクを要求時に実行」
   - ✅ 「スケジュールに従ってタスクを実行」
   - 「タスクが実行中の場合の規則」: 新しいインスタンスを実行しない（推奨）

### パスの指定方法

#### 推奨（フルパス）

```powershell
-ExecutionPolicy Bypass -NoProfile -File "C:\Users\sohta\equity01\ops\run_executor_dryrun_scheduler.ps1"
```

#### 開始ディレクトリの設定

「開始ディレクトリ（オプション）」に以下を設定：
```
C:\Users\sohta\equity01
```

### エラーコード

#### 0xFFFD0000 エラーについて

このエラーコードが発生する場合、以下の原因が考えられます：

1. **パスの問題**
   - フルパスを使用しているか確認
   - パスにスペースや特殊文字が含まれていないか確認
   - 引用符で囲まれているか確認

2. **権限の問題**
   - 「最高の権限で実行する」を有効にする
   - タスクの実行アカウントが適切か確認

3. **実行ポリシー**
   - `-ExecutionPolicy Bypass` が指定されているか確認

#### 対処法

1. **スクリプトパスを確認**
   ```powershell
   Test-Path "C:\Users\sohta\equity01\ops\run_executor_dryrun_scheduler.ps1"
   ```

2. **手動実行で確認**
   ```powershell
   powershell -ExecutionPolicy Bypass -NoProfile -File "C:\Users\sohta\equity01\ops\run_executor_dryrun_scheduler.ps1"
   ```

3. **ログを確認**
   - `executor_runs/logs/run_executor_dryrun_*.log` を確認

### Exit Code

| Exit Code | 意味 | タスクスケジューラでの扱い |
|-----------|------|---------------------------|
| 0 | 成功（PRE_SUBMIT到達）またはHALT | ✅ 成功 |
| 1 | 例外（想定外エラー） | ❌ 失敗 |

**重要**: `run_executor_dryrun_scheduler.ps1` を使用すると、exit code 2（HALT）が 0 に変換されるため、タスクスケジューラで「成功」として扱われます。

### トラブルシューティング

1. **ログファイルを確認**
   - `executor_runs/logs/run_executor_dryrun_*.log`

2. **手動実行で確認**
   - タスクスケジューラと同じアカウントで手動実行

3. **パスを確認**
   - フルパスを使用しているか
   - ディレクトリが存在するか

4. **権限を確認**
   - 実行アカウントがファイルにアクセスできるか

