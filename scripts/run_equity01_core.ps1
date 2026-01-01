#!/usr/bin/env pwsh
# -*- coding: utf-8 -*-
# equity01-JP: Core Pipeline Execution Script for Windows Task Scheduler
#
# 目的:
# - equity01-JP の「実運営 core パイプライン」を自動実行
# - analysis / deprecated は一切実行しない
# - 実行対象は core のみ
# - 失敗時に静かに止まり、ログだけ残す（自動リトライなし）
#
# 実行例（タスクマネージャ）:
#   powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\equity01\scripts\run_equity01_core.ps1"

# エラー時に即座に停止
$ErrorActionPreference = "Stop"

# プロジェクトルートを自動検出（このスクリプトの場所基準）
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath

# ログディレクトリを作成
$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

# ログローテーション（30日以上古いログを削除）
$CutoffDate = (Get-Date).AddDays(-30)
Get-ChildItem -Path $LogsDir -Filter "run_equity01_core_*.log" -ErrorAction SilentlyContinue | 
    Where-Object { $_.LastWriteTime -lt $CutoffDate } | 
    Remove-Item -Force -ErrorAction SilentlyContinue

# ログファイル名（YYYYMMDD形式）
$LogDate = Get-Date -Format "yyyyMMdd"
$LogFile = Join-Path $LogsDir "run_equity01_core_$LogDate.log"

# ログ関数
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    Add-Content -Path $LogFile -Value $LogMessage
    Write-Host $LogMessage
}

# エラーログ関数
function Write-ErrorLog {
    param(
        [string]$Message
    )
    Write-Log -Message $Message -Level "ERROR"
}

# Python実行パスの検出
function Get-PythonPath {
    $VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        return $VenvPython
    }
    
    # venvがない場合はシステムのpythonを使用
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCmd) {
        return $PythonCmd.Source
    }
    
    throw "Pythonが見つかりません。venvを有効化するか、システムにPythonをインストールしてください。"
}

# スクリプト実行関数
function Invoke-CoreScript {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )
    
    $ScriptName = Split-Path -Leaf $ScriptPath
    Write-Log "========================================"
    Write-Log "START: $ScriptName"
    
    try {
        $PythonPath = Get-PythonPath
        $FullScriptPath = Join-Path $ProjectRoot $ScriptPath
        
        if (-not (Test-Path $FullScriptPath)) {
            throw "スクリプトが見つかりません: $FullScriptPath"
        }
        
        # Pythonスクリプトを実行（標準出力・標準エラーをログに記録）
        # シンプルな方法：2>&1で標準出力と標準エラーをキャプチャ
        Push-Location $ProjectRoot
        try {
            # 【F. PowerShell エラーハンドリングの是正】
            # 成否判定は Python プロセスの ExitCode のみで行う
            # stdout/stderr の文字列内容（Traceback含有など）では判定しない
            
            # ErrorActionPreferenceを一時的にContinueに変更（ErrorRecordを例外として扱わない）
            # これにより、Pythonの標準エラー出力がErrorRecordとして扱われても例外にならない
            $OldErrorAction = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            
            try {
                # Pythonスクリプトを実行（標準出力・標準エラーをキャプチャ）
                $AllOutput = & $PythonPath $FullScriptPath $Arguments 2>&1
            }
            finally {
                $ErrorActionPreference = $OldErrorAction
            }
            
            # 【重要】$LASTEXITCODEを取得（実行直後に取得する必要がある）
            # $LASTEXITCODEは手動でリセットしない（正しい終了コードを取得するため）
            $ExitCode = $LASTEXITCODE
            # $ExitCodeが$nullの場合は、Pythonスクリプトが正常に終了したと判断（デフォルトで0とする）
            if ($null -eq $ExitCode -or $ExitCode -eq "") {
                $ExitCode = 0
            }
            
            # 出力をログに記録（ErrorRecordはログ出力のみ、判定には使用しない）
            $PythonOutput = @()
            foreach ($line in $AllOutput) {
                $lineStr = $line.ToString()
                if ($line -is [System.Management.Automation.ErrorRecord]) {
                    # RemoteExceptionやCategoryInfoは無視（Pythonの正常出力の一部）
                    # PowerShellがPythonの標準エラー出力をErrorRecordとして扱う場合があるが、これは正常
                    if ($lineStr -notmatch "CategoryInfo|RemoteException|FullyQualifiedErrorId|NotSpecified") {
                        # ログには記録するが、エラー判定には使用しない
                        Add-Content -Path $LogFile -Value "STDERR: $lineStr"
                        Write-Host "STDERR: $lineStr" -ForegroundColor Yellow
                    }
                }
                else {
                    # Pythonスクリプトの実際の出力を記録
                    $PythonOutput += $lineStr
                    Add-Content -Path $LogFile -Value $lineStr
                    Write-Host $lineStr
                }
            }
            
            # 【重要】エラーチェック：終了コードが0以外の場合のみエラーとする
            # - stdout/stderr の文字列内容（Traceback含有など）では判定しない
            # - Pythonスクリプトが exit 0 で終了した場合は成功扱い
            # - try/catch に入るのは PowerShell 自身の例外（起動不能等）のみ
            if ($ExitCode -ne 0) {
                $ErrorMsg = "スクリプト実行失敗 (ExitCode: $ExitCode): $ScriptName"
                # エラー時の詳細情報として出力を追加（判定には使用しない）
                if ($PythonOutput) {
                    $ErrorLines = $PythonOutput | Where-Object { 
                        $_ -match "Traceback|FileNotFoundError|KeyError|ValueError|ImportError|SyntaxError|IndentationError"
                    }
                    if ($ErrorLines) {
                        $ErrorMsg += "`n詳細: $($ErrorLines -join "`n")"
                    }
                }
                throw $ErrorMsg
            }
        }
        catch {
            # PowerShell自身の例外（Python起動不能など）のみここに入る
            # Pythonが exit 0 の場合は上記のif文を通らないため、ここには入らない
            Write-ErrorLog "PowerShell例外: $ScriptName - $($_.Exception.Message)"
            throw
        }
        finally {
            Pop-Location
        }
        
        Write-Log "OK: $ScriptName"
    }
    catch {
        Write-ErrorLog "エラー: $ScriptName - $($_.Exception.Message)"
        if ($_.ScriptStackTrace) {
            Write-ErrorLog "スタックトレース: $($_.ScriptStackTrace)"
        }
        throw
    }
}

# ============================================================================
# メイン処理
# ============================================================================

try {
    Write-Log "========================================"
    Write-Log "equity01-JP Core Pipeline 実行開始"
    Write-Log "プロジェクトルート: $ProjectRoot"
    Write-Log "ログファイル: $LogFile"
    Write-Log "========================================"
    
    # Pythonパスの確認
    $PythonPath = Get-PythonPath
    Write-Log "Pythonパス: $PythonPath"
    
    # 1. ユニバース構築
    Invoke-CoreScript -ScriptPath "scripts\core\universe_builder.py" -Arguments @("--config", "configs\universe.yml")
    
    # 2. 価格データ取得
    $UniversePath = Join-Path $ProjectRoot "data\intermediate\universe\latest_universe.parquet"
    if (-not (Test-Path $UniversePath)) {
        throw "ユニバースファイルが見つかりません: $UniversePath"
    }
    # 2. 価格データ取得
    # download_prices.pyのPROJECT_ROOTは既にequity01に設定済み（parents[2]）
    Invoke-CoreScript -ScriptPath "scripts\core\download_prices.py" -Arguments @("--universe", "data\intermediate\universe\latest_universe.parquet")
    
    # 3. TOPIXデータ構築（data配下に移動済み）
    $TpxScriptPath = Join-Path $ProjectRoot "scripts\data\build_index_tpx_daily.py"
    if (Test-Path $TpxScriptPath) {
        Invoke-CoreScript -ScriptPath "scripts\data\build_index_tpx_daily.py"
    }
    else {
        Write-Log "WARN: build_index_tpx_daily.py が見つかりません。スキップします。"
    }
    
    # 4. 特徴量構築（内部でスコアリングも実行される）
    # 【② run_scoring 二重実行の回避】
    # build_features.py内でcompute_scores_allを呼び出しているため、
    # run_scoring.pyを別途実行すると二重実行となる
    # 設計として：build_features.py内でスコアリングを実行し、ps1からrun_scoring.pyは呼ばない
    Invoke-CoreScript -ScriptPath "scripts\core\build_features.py"
    
    # 5. ポートフォリオ構築（運用終点生成）★最重要
    Invoke-CoreScript -ScriptPath "scripts\core\build_portfolio.py"
    
    # 実行結果の確認
    $OutputPath = Join-Path $ProjectRoot "data\processed\daily_portfolio_guarded.parquet"
    if (Test-Path $OutputPath) {
        $FileInfo = Get-Item $OutputPath
        Write-Log "========================================"
        Write-Log "SUCCESS: 運用終点ファイルが生成されました"
        Write-Log "  ファイル: $OutputPath"
        Write-Log "  サイズ: $($FileInfo.Length) bytes"
        Write-Log "  更新日時: $($FileInfo.LastWriteTime)"
        Write-Log "========================================"
    }
    else {
        Write-ErrorLog "WARNING: 運用終点ファイルが生成されていません: $OutputPath"
        throw "運用終点ファイルの生成を確認できませんでした"
    }
    
    Write-Log "========================================"
    Write-Log "equity01-JP Core Pipeline 実行完了"
    Write-Log "========================================"
    
    exit 0
}
catch {
    Write-ErrorLog "========================================"
    Write-ErrorLog "FATAL ERROR: Core Pipeline 実行失敗"
    Write-ErrorLog "エラーメッセージ: $($_.Exception.Message)"
    Write-ErrorLog "========================================"
    exit 1
}

