"""
run_execution_dryrun.py

execution dry-runの実行入口（scripts/opsから実行可能）。
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.run_dryrun import main

if __name__ == "__main__":
    main()
