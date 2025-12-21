#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/run_all_stop_comparison.py

全ての戦略・ウィンドウについて eval_stop_regimes.py vs backtest_from_weights_with_stop.py を比較

実行順序:
1. eval_stop_regimes.py を実行（全戦略を生成）
2. backtest_from_weights_with_stop.py を各戦略・ウィンドウで実行
3. compare_eval_vs_weights_stop.py で比較
"""

import sys
import io
import os
from pathlib import Path
import subprocess

# Windows環境での文字化け対策
if sys.platform == 'win32':
    # 環境変数を設定
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 標準出力のエンコーディングをUTF-8に設定
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.7以前の互換性
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # 既に設定されている場合はスキップ
        pass

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def run_command(cmd: list, description: str, cwd: Path = None, log_file: Path = None) -> bool:
    """
    コマンドを実行する
    
    Returns
    -------
    bool
        成功した場合True
    """
    print("\n" + "=" * 80)
    print(f"[実行中] {description}")
    print("=" * 80)
    print(f"コマンド: {' '.join(cmd)}")
    if cwd:
        print(f"作業ディレクトリ: {cwd}")
    
    try:
        # Windows環境での文字化け対策: UTF-8で実行
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(
            cmd,
            check=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # エラー時は置換
            env=env  # 環境変数を設定
        )
        
        # 標準出力に表示
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        # ログファイルにも書き込む（UTF-8で）
        if log_file:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"[実行中] {description}\n")
                    f.write(f"{'='*80}\n")
                    f.write(f"コマンド: {' '.join(cmd)}\n")
                    if cwd:
                        f.write(f"作業ディレクトリ: {cwd}\n")
                    f.write(result.stdout)
                    if result.stderr:
                        f.write("\n[stderr]\n")
                        f.write(result.stderr)
                    f.write(f"\n[OK] {description} 成功\n")
            except Exception as e:
                print(f"[WARN] ログファイルへの書き込みに失敗: {e}")
        
        print(f"\n[OK] {description} 成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[NG] {description} 失敗 (exit code: {e.returncode})")
        print(f"stdout:\n{e.stdout}")
        print(f"stderr:\n{e.stderr}", file=sys.stderr)
        return False


def main():
    """メイン処理"""
    # ログファイルのパスを設定
    log_file = ROOT_DIR / "data" / "processed" / "research" / "reports" / "run_all_stop_comparison.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # ログファイルをクリア
    if log_file.exists():
        log_file.unlink()
    
    print("=" * 80)
    print("=== eval_stop_regimes vs backtest_from_weights_with_stop 一括比較 ===")
    print("=" * 80)
    print(f"[INFO] ログファイル: {log_file}")
    
    # Python実行ファイルのパス（環境に応じて調整）
    python_cmd = sys.executable
    
    # 1. eval_stop_regimes.py を実行
    print("\n" + "=" * 80)
    print("[STEP 1] eval_stop_regimes.py を実行中...")
    print("=" * 80)
    
    eval_script = ROOT_DIR / "scripts" / "analysis" / "eval_stop_regimes.py"
    if not eval_script.exists():
        print(f"✗ スクリプトが見つかりません: {eval_script}")
        return 1
    
    # eval_stop_regimes.pyは引数なしで実行（全戦略を生成）
    cmd_eval = [python_cmd, str(eval_script.relative_to(ROOT_DIR))]
    
    if not run_command(cmd_eval, "eval_stop_regimes.py実行", cwd=ROOT_DIR, log_file=log_file):
        print("\n⚠️  警告: eval_stop_regimes.py が失敗しました。処理を続行します。")
    
    # 2. backtest_from_weights_with_stop.py を各戦略・ウィンドウで実行
    print("\n" + "=" * 80)
    print("[STEP 2] backtest_from_weights_with_stop.py を各戦略・ウィンドウで実行中...")
    print("=" * 80)
    
    strategies = ["stop0", "planA", "planB"]
    windows = [60, 120]
    
    backtest_script = ROOT_DIR / "scripts" / "analysis" / "backtest_from_weights_with_stop.py"
    
    success_count = 0
    total_count = len(strategies) * len(windows)
    
    for strategy in strategies:
        for window in windows:
            cmd_backtest = [
                python_cmd,
                str(backtest_script.relative_to(ROOT_DIR)),
                "--strategy", strategy,
                "--window", str(window),
            ]
            
            if run_command(cmd_backtest, f"backtest_from_weights_with_stop.py ({strategy}, w{window})", cwd=ROOT_DIR, log_file=log_file):
                success_count += 1
    
    print(f"\n[結果] backtest_from_weights_with_stop.py: {success_count}/{total_count} 成功")
    
    if success_count == 0:
        print("\n[NG] STEP 2 失敗: 処理を中断します")
        return 1
    
    # 3. compare_eval_vs_weights_stop.py で比較
    print("\n" + "=" * 80)
    print("[STEP 3] 比較を実行中...")
    print("=" * 80)
    
    compare_script = ROOT_DIR / "scripts" / "analysis" / "compare_eval_vs_weights_stop.py"
    
    comparison_success = 0
    comparison_total = 0
    
    for strategy in strategies:
        for window in windows:
            cmd_compare = [
                python_cmd,
                str(compare_script.relative_to(ROOT_DIR)),
                "--strategy", strategy,
                "--window", str(window),
            ]
            
            comparison_total += 1
            if run_command(cmd_compare, f"比較 ({strategy}, w{window})", cwd=ROOT_DIR, log_file=log_file):
                comparison_success += 1
    
    print(f"\n[結果] 比較: {comparison_success}/{comparison_total} 成功")
    
    # サマリー表示
    print("\n" + "=" * 80)
    print("=== 実行サマリー ===")
    print("=" * 80)
    print(f"backtest実行: {success_count}/{total_count}")
    print(f"比較実行: {comparison_success}/{comparison_total}")
    
    if comparison_success == comparison_total:
        print("\n[OK] 全ての比較が完了しました")
        print(f"詳細は data/processed/research/reports/eval_vs_weights_comparison_summary.csv を確認してください")
        print(f"ログファイル: {log_file}")
        
        # ログファイルにサマリーを追記
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "="*80 + "\n")
                f.write("=== 実行サマリー ===\n")
                f.write("="*80 + "\n")
                f.write(f"backtest実行: {success_count}/{total_count}\n")
                f.write(f"比較実行: {comparison_success}/{comparison_total}\n")
        except Exception as e:
            print(f"[WARN] ログファイルへの書き込みに失敗: {e}")
        
        return 0
    else:
        print(f"\n[WARN] 一部の比較が失敗しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())

