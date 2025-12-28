#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/stg_sanity_check.py

stgの最低限整合性チェック（import + 軽い存在チェック）

目的：
- stgのweights型（core）スクリプトが正常にimportできることを確認
- 主要関数・エントリ関数が存在することを確認
- 生成物パスが存在するかをチェック（あれば）

注意：
- 重いbacktestは回さない（実行時間を短く）
- CursorのRunを一本化するためのスクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import importlib.util
from typing import List, Tuple


def check_module_import(module_path: Path, module_name: str) -> Tuple[bool, str]:
    """
    モジュールが正常にimportできるかチェック
    
    Returns
    -------
    (success: bool, message: str)
    """
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            return False, f"Failed to load spec: {module_path}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True, f"OK: {module_path.name}"
    except Exception as e:
        return False, f"ERROR: {module_path.name} - {str(e)}"


def check_function_exists(module_path: Path, function_name: str) -> Tuple[bool, str]:
    """
    モジュール内に関数が存在するかチェック
    
    Returns
    -------
    (success: bool, message: str)
    """
    try:
        module_name = module_path.stem
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            return False, f"Failed to load spec: {module_path}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                return True, f"OK: {module_path.name}.{function_name}() exists"
            else:
                return False, f"ERROR: {module_path.name}.{function_name} is not callable"
        else:
            return False, f"ERROR: {module_path.name}.{function_name} not found"
    except Exception as e:
        return False, f"ERROR: {module_path.name}.{function_name} - {str(e)}"


def check_path_exists(path: Path) -> Tuple[bool, str]:
    """
    パスが存在するかチェック
    
    Returns
    -------
    (success: bool, message: str)
    """
    if path.exists():
        if path.is_file():
            return True, f"OK: {path} exists (file)"
        elif path.is_dir():
            return True, f"OK: {path} exists (directory)"
        else:
            return False, f"ERROR: {path} exists but is not file/directory"
    else:
        return False, f"WARN: {path} does not exist"


def main():
    """メイン関数"""
    print("=" * 80)
    print("stg sanity check")
    print("=" * 80)
    print()
    
    errors: List[str] = []
    warnings: List[str] = []
    
    # 1. core 5ファイルのimportチェック
    print("[1] Core scripts import check")
    print("-" * 80)
    
    core_scripts = [
        ("scripts/analysis/generate_variant_weights.py", "generate_variant_weights"),
        ("scripts/analysis/build_cross4_target_weights.py", "build_cross4_target_weights"),
        ("scripts/analysis/build_cross4_target_weights_with_stop.py", "build_cross4_target_weights_with_stop"),
        ("scripts/analysis/backtest_from_weights.py", "backtest_from_weights"),
        ("scripts/analysis/backtest_from_weights_with_stop.py", "backtest_from_weights_with_stop"),
    ]
    
    for script_path_str, module_name in core_scripts:
        script_path = ROOT_DIR / script_path_str
        if not script_path.exists():
            error_msg = f"ERROR: {script_path_str} does not exist"
            print(error_msg)
            errors.append(error_msg)
            continue
        
        success, message = check_module_import(script_path, module_name)
        print(f"  {message}")
        if not success:
            errors.append(message)
    
    print()
    
    # 2. 主要関数の存在チェック
    print("[2] Core functions existence check")
    print("-" * 80)
    
    function_checks = [
        ("scripts/analysis/generate_variant_weights.py", "main"),
        ("scripts/analysis/build_cross4_target_weights.py", "main"),
        ("scripts/analysis/build_cross4_target_weights_with_stop.py", "main"),
        ("scripts/analysis/backtest_from_weights.py", "calculate_returns_from_weights"),
        ("scripts/analysis/backtest_from_weights_with_stop.py", "main"),
    ]
    
    for script_path_str, function_name in function_checks:
        script_path = ROOT_DIR / script_path_str
        if not script_path.exists():
            continue  # 既に[1]でエラーを報告済み
        
        success, message = check_function_exists(script_path, function_name)
        print(f"  {message}")
        if not success:
            warnings.append(message)  # 関数が見つからなくても警告程度
    
    print()
    
    # 3. 生成物パスの存在チェック（あれば）
    print("[3] Output paths existence check (optional)")
    print("-" * 80)
    
    output_paths = [
        Path("data/processed/weights"),
        Path("data/processed/weights_bt"),
        Path("data/processed/daily_portfolio_guarded.parquet"),
    ]
    
    for path in output_paths:
        full_path = ROOT_DIR / path
        success, message = check_path_exists(full_path)
        print(f"  {message}")
        if not success and "WARN" in message:
            warnings.append(message)
    
    print()
    
    # 結果サマリ
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    if errors:
        print(f"❌ Errors: {len(errors)}")
        for error in errors:
            print(f"  - {error}")
        return 1
    elif warnings:
        print(f"⚠️  Warnings: {len(warnings)}")
        for warning in warnings:
            print(f"  - {warning}")
        print("✅ No errors (warnings only)")
        return 0
    else:
        print("✅ All checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())

