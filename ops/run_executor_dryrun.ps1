<#
.SYNOPSIS
executor dry-run実行スクリプト

.DESCRIPTION
executor dry-runを実行し、ログを保存する。
ExitCodeはpython側の値を尊重（0: 成功, 2: HALT, 1: 例外）

.PARAMETER RepoRoot
リポジトリルート（デフォルト: スクリプトの親ディレクトリ）

.PARAMETER VenvDir
仮想環境ディレクトリ（デフォルト: .venv）

.PARAMETER PyRel
Python実行ファイルの相対パス（デフォルト: Scripts\python.exe）

.PARAMETER Script
実行するPythonスクリプト（デフォルト: scripts\ops\run_executor_dryrun.py）

.PARAMETER LogDir
ログディレクトリ（デフォルト: executor_runs\logs）

.PARAMETER NoTimestamp
タイムスタンプなしでログファイル名を"latest"にする

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\ops\run_executor_dryrun.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\ops\run_executor_dryrun.ps1 -RepoRoot "C:\Users\sohta\equity01"
#>
param(
  [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path,
  [string]$VenvDir  = ".venv",
  [string]$PyRel    = "Scripts\python.exe",
  [string]$Script   = "scripts\ops\run_executor_dryrun.py",
  [string]$LogDir   = "executor_runs\logs",
  [switch]$NoTimestamp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
  $full = Join-Path $RepoRoot $p
  if (-not (Test-Path $full)) { 
    New-Item -ItemType Directory -Path $full -Force | Out-Null 
  }
  return $full
}

# --- Paths ---
$python = Join-Path (Join-Path $RepoRoot $VenvDir) $PyRel
if (-not (Test-Path $python)) {
  throw "python not found: $python"
}

$scriptPath = Join-Path $RepoRoot $Script
if (-not (Test-Path $scriptPath)) {
  throw "script not found: $scriptPath"
}

$logDirFull = Ensure-Dir $LogDir

# --- Log file name ---
$ts = if ($NoTimestamp) { "latest" } else { (Get-Date -Format "yyyyMMdd_HHmmss") }
$logFile = Join-Path $logDirFull "run_executor_dryrun_$ts.log"

# --- Run ---
Push-Location $RepoRoot
try {
  # 文字化け対策（UTF-8）
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $PSDefaultParameterValues['Out-File:Encoding'] = 'UTF8'

  # 実行開始ログ
  $startTime = Get-Date
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines($logFile, @(
    "========================================",
    "executor dry-run execution started",
    "Start time: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))",
    "Repository root: $RepoRoot",
    "Python: $python",
    "Script: $scriptPath",
    "========================================",
    ""
  ), $utf8NoBom)

  # 実行：stdout/stderrを両方ログへ
  $output = & $python $scriptPath 2>&1
  $output | Out-File -FilePath $logFile -Encoding UTF8 -Append
  $output | Write-Host
  $exit = $LASTEXITCODE

  # 実行終了ログ
  $endTime = Get-Date
  $duration = $endTime - $startTime
  "" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "========================================" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "executor dry-run execution finished" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "End time: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "Duration: $($duration.TotalSeconds) seconds" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "ExitCode: $exit" | Out-File -FilePath $logFile -Encoding UTF8 -Append
  "========================================" | Out-File -FilePath $logFile -Encoding UTF8 -Append

  # ExitCodeはpython側の値を尊重（0/2/1）
  exit $exit
}
catch {
  # 想定外例外はexit 1
  $errorMsg = "FATAL: $($_.Exception.Message)"
  $errorMsg | Out-File -FilePath $logFile -Encoding UTF8 -Append
  $errorMsg | Write-Host
  Write-Host $_.ScriptStackTrace
  exit 1
}
finally {
  Pop-Location
}

