"""
scripts/ops/run_executor_dryrun.py

executor dry-run実行のエントリポイント（1本化）

core成果物を読み込み、executor.build_intent -> executor.precheck -> executor.dryrun
を実行し、RunLogを生成する。

exit code:
  - 0: 成功
  - 2: HALT（事前チェック失敗等）
  - 1: 例外
"""
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from executor.dryrun import run_dryrun_pre_submit
from executor.config_loader import load_execution_config
from executor.models import ExecutionConfig


def main() -> int:
    """
    メイン実行
    
    Returns
    -------
    int
        exit code（0: 成功, 2: HALT, 1: 例外）
    """
    try:
        # 設定読み込み
        config = load_execution_config()
        
        # dry-run実行
        run = run_dryrun_pre_submit(
            config=config,
            mode="DRYRUN_PRE_SUBMIT",
            stop_before_submit=True,
        )
        
        # exit codeを決定
        stop_reason = run.results.get("stop_reason")
        
        if stop_reason == "STOP_BEFORE_SUBMIT":
            # 正常終了（PRE_SUBMITで停止）
            print(f"\n[OK] executor dry-run完了: {run.run_id}")
            print(f"   latest_date: {run.latest_date}")
            print(f"   order_intents: {len(run.order_intents)} 件")
            print(f"   hedge_intents: {len(run.hedge_intents)} 件")
            return 0
        
        elif stop_reason == "PRECHECK_FAILED":
            # 事前チェック失敗（HALT）
            print(f"\n[WARN] executor dry-run停止（事前チェック失敗）: {run.run_id}")
            errors = run.results.get("errors", [])
            for error in errors:
                print(f"   - {error.get('reason', error.get('error_message'))}")
            return 2
        
        elif stop_reason == "ERROR":
            # 例外発生
            print(f"\n[ERROR] executor dry-runエラー: {run.run_id}")
            errors = run.results.get("errors", [])
            for error in errors:
                print(f"   - {error.get('error_type')}: {error.get('error_message')}")
            return 1
        
        else:
            # その他の停止理由
            print(f"\n[WARN] executor dry-run停止: {run.run_id} (stop_reason: {stop_reason})")
            return 1
    
    except Exception as e:
        print(f"\n[ERROR] executor dry-run実行時例外: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

