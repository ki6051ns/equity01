<#
.SYNOPSIS
executor dry-run実行スクリプト（タスクスケジューラ用）

.DESCRIPTION
executor dry-runを実行し、ログを保存する。
タスクスケジューラ用：exit code 2（HALT）も正常終了（0）として扱う。

Exit Code:
  0: 成功（PRE_SUBMIT到達）またはHALT（事前チェック失敗）
  1: 例外（想定外エラー）

.PARAMETER RepoRoot
リポジトリルート（デフォルト: スクリプトの親ディレクトリ）

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\ops\run_executor_dryrun_scheduler.ps1
#>
param(
  [string]$RepoRoot = $null
)

# エラー時に即座に停止
$ErrorActionPreference = "Stop"

# プロジェクトルートを自動検出（このスクリプトの場所基準）
if ($null -eq $RepoRoot -or $RepoRoot -eq "") {
  $ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
  $RepoRoot = Split-Path -Parent $ScriptPath
}

# パスを正規化
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)

# 元のスクリプトを実行
$scriptPath = Join-Path $RepoRoot "ops\run_executor_dryrun.ps1"
if (-not (Test-Path $scriptPath)) {
  $errorMsg = "run_executor_dryrun.ps1 not found: $scriptPath"
  Write-Host $errorMsg
  exit 1
}

# 作業ディレクトリを設定
Push-Location $RepoRoot
try {
  # 元のスクリプトを実行
  & $scriptPath -RepoRoot $RepoRoot
  $exit = $LASTEXITCODE
  
  # exit code 2（HALT）も正常終了として扱う
  # HALT = 事前チェック失敗（休日・価格stale・余力不足など）は正常な停止
  if ($exit -eq 2) {
    Write-Host "HALT detected (exit code 2) - treated as success for scheduler"
    exit 0
  }
  
  # exit code 0または1はそのまま返す
  exit $exit
}
catch {
  $errorMsg = "FATAL: $($_.Exception.Message)"
  Write-Host $errorMsg
  if ($_.ScriptStackTrace) {
    Write-Host $_.ScriptStackTrace
  }
  exit 1
}
finally {
  Pop-Location
}

