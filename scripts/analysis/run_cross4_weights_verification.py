#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/analysis/run_cross4_weights_verification.py

cross4 weights版検証フローを一括実行するスクリプト

実行順序:
① variant別/horizon別のweightsを生成
② cross4 target weightsを生成
③ weights→returnsを計算
④ 一致検証
"""

import sys
import subprocess
from pathlib import Path

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[2]  # scripts/analysis/run_*.py から2階層上
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse


def run_command(cmd: list, description: str, cwd: Path = None) -> bool:
    """
    コマンドを実行し、成功/失敗を返す
    
    Parameters
    ----------
    cmd : list
        実行するコマンド（subprocess.run用）
    description : str
        実行内容の説明
    cwd : Path, optional
        作業ディレクトリ（デフォルト: プロジェクトルート）
    
    Returns
    -------
    bool
        成功した場合True、失敗した場合False
    """
    if cwd is None:
        cwd = ROOT_DIR
    
    print("\n" + "=" * 80)
    print(f"[実行中] {description}")
    print("=" * 80)
    print(f"コマンド: {' '.join(cmd)}")
    print(f"作業ディレクトリ: {cwd}")
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True,
            cwd=str(cwd)
        )
        print(f"\n✓ {description} 完了")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ {description} 失敗 (exit code: {e.returncode})")
        return False
    except Exception as e:
        print(f"\n✗ {description} エラー: {e}")
        return False


def generate_variant_weights(horizons: list = None, variants: list = None) -> bool:
    """
    ① variant別/horizon別のweightsを生成
    
    Parameters
    ----------
    horizons : list, optional
        実行するhorizonのリスト（デフォルト: [1, 5, 10, 60, 90, 120]）
    variants : list, optional
        実行するvariantのリスト（デフォルト: ["rank", "zdownvol"]）
    
    Returns
    -------
    bool
        すべて成功した場合True、いずれかが失敗した場合False
    """
    if horizons is None:
        horizons = [1, 5, 10, 60, 90, 120]
    if variants is None:
        variants = ["rank", "zdownvol"]
    
    # 現在のスクリプトのディレクトリを基準にパスを構築
    current_dir = Path(__file__).resolve().parent
    script_path = current_dir / "generate_variant_weights.py"
    
    success_count = 0
    total_count = 0
    
    for variant in variants:
        for horizon in horizons:
            # ladder方式の判定: horizon >= 60 は ladder、それ以外は nonladder
            ladder_type = "ladder" if horizon >= 60 else "nonladder"
            
            # スクリプトパスをプロジェクトルートからの相対パスに変換
            script_rel_path = script_path.resolve().relative_to(ROOT_DIR.resolve())
            
            cmd = [
                sys.executable,
                str(script_rel_path),
                "--variant", variant,
                "--horizon", str(horizon),
                "--ladder", ladder_type
            ]
            
            description = f"weights生成: {variant} H{horizon} ({ladder_type})"
            total_count += 1
            
            if run_command(cmd, description, cwd=ROOT_DIR):
                success_count += 1
            else:
                print(f"\n⚠️  警告: {description} が失敗しました。処理を続行します。")
                # 失敗しても続行（後続のステップでエラーが出る場合はそこで停止）
    
    print(f"\n[結果] weights生成: {success_count}/{total_count} 成功")
    return success_count == total_count


def build_cross4_target_weights() -> bool:
    """
    ② cross4 target weightsを生成
    
    Returns
    -------
    bool
        成功した場合True、失敗した場合False
    """
    current_dir = Path(__file__).resolve().parent
    script_path = current_dir / "build_cross4_target_weights.py"
    script_rel_path = script_path.resolve().relative_to(ROOT_DIR.resolve())
    cmd = [sys.executable, str(script_rel_path)]
    
    return run_command(cmd, "cross4 target weights生成", cwd=ROOT_DIR)


def backtest_from_weights() -> bool:
    """
    ③ weights→returnsを計算
    
    Returns
    -------
    bool
        成功した場合True、失敗した場合False
    """
    current_dir = Path(__file__).resolve().parent
    script_path = current_dir / "backtest_from_weights.py"
    script_rel_path = script_path.resolve().relative_to(ROOT_DIR.resolve())
    cmd = [sys.executable, str(script_rel_path)]
    
    return run_command(cmd, "weights→returns計算", cwd=ROOT_DIR)


def verify_cross4_equivalence() -> bool:
    """
    ④ 一致検証
    
    Returns
    -------
    bool
        成功した場合True、失敗した場合False
    """
    current_dir = Path(__file__).resolve().parent
    script_path = current_dir / "verify_cross4_equivalence.py"
    script_rel_path = script_path.resolve().relative_to(ROOT_DIR.resolve())
    cmd = [sys.executable, str(script_rel_path)]
    
    return run_command(cmd, "一致検証", cwd=ROOT_DIR)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="cross4 weights版検証フローを一括実行"
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="実行するステップを指定（1-4、指定しない場合はすべて実行）"
    )
    parser.add_argument(
        "--skip-weights",
        action="store_true",
        help="① weights生成をスキップ（既に生成済みの場合）"
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=None,
        help="実行するhorizonのリスト（デフォルト: 1 5 10 60 90 120）"
    )
    parser.add_argument(
        "--variants",
        type=str,
        nargs="+",
        choices=["rank", "zdownvol"],
        default=None,
        help="実行するvariantのリスト（デフォルト: rank zdownvol）"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("=== cross4 weights版検証フロー一括実行 ===")
    print("=" * 80)
    
    # ステップ指定がある場合はそのステップのみ実行
    if args.step:
        steps_to_run = [args.step]
    else:
        steps_to_run = [1, 2, 3, 4]
    
    # ① variant別/horizon別のweightsを生成
    if 1 in steps_to_run and not args.skip_weights:
        print("\n" + "=" * 80)
        print("[STEP 1] variant別/horizon別のweightsを生成")
        print("=" * 80)
        if not generate_variant_weights(args.horizons, args.variants):
            print("\n✗ STEP 1 失敗: 処理を中断します")
            return 1
    
    # ② cross4 target weightsを生成
    if 2 in steps_to_run:
        print("\n" + "=" * 80)
        print("[STEP 2] cross4 target weightsを生成")
        print("=" * 80)
        if not build_cross4_target_weights():
            print("\n✗ STEP 2 失敗: 処理を中断します")
            return 1
    
    # ③ weights→returnsを計算
    if 3 in steps_to_run:
        print("\n" + "=" * 80)
        print("[STEP 3] weights→returnsを計算")
        print("=" * 80)
        if not backtest_from_weights():
            print("\n✗ STEP 3 失敗: 処理を中断します")
            return 1
    
    # ④ 一致検証
    if 4 in steps_to_run:
        print("\n" + "=" * 80)
        print("[STEP 4] 一致検証")
        print("=" * 80)
        if not verify_cross4_equivalence():
            print("\n✗ STEP 4 失敗")
            return 1
        else:
            print("\n" + "=" * 80)
            print("✓ すべてのステップが完了しました")
            print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

