"""
executor: Intent-based execution module

core（数理・αβ・STOP）は完全一致検証を通過して確定。
executorを正本として、実行系を固める。

設計原則:
- Intent-based: 計算（core）と実行（executor）を分離
- Fail-safe: 休日・通信・余力・価格stale時は「止まる」
- Idempotent: 同日再実行 → 同一 Intent / 同一結果
- Audit-first: 何を判断し、なぜ止めたかがログで追える
"""
from executor.models import OrderIntent, HedgeIntent, RunLog, ExecutionConfig
from executor.precheck import run_prechecks, PrecheckResult
from executor.config_loader import load_execution_config

__all__ = [
    "OrderIntent",
    "HedgeIntent",
    "RunLog",
    "ExecutionConfig",
    "run_prechecks",
    "PrecheckResult",
    "load_execution_config",
]

