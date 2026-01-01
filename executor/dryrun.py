"""
executor/dryrun.py

Dry-run実行（PRE_SUBMITモード）
注文画面まで進み、最終クリックだけ実行しない。
"""
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import date, datetime
import json
import uuid
import sys
import hashlib

import pandas as pd

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from executor.models import RunLog, OrderIntent, HedgeIntent, ExecutionConfig
from executor.build_intent import (
    build_order_intents_from_core,
    build_hedge_intents_from_core,
)
from executor.precheck import run_prechecks
from executor.config_loader import load_execution_config
from executor.adapters.sbi_cash import SBICashAdapter
from executor.adapters.sbi_cfd import SBICFDAdapter
from executor.log_writer import write_order_intent_csv


def save_run_log(
    run: RunLog,
    archive_dir: Path = None,
) -> Path:
    """
    実行ログを保存
    
    Parameters
    ----------
    run : ExecutionRun
        実行ログ
    archive_dir : Path or None
        アーカイブディレクトリ（デフォルト: executor/archives/runs）
    
    Returns
    -------
    Path
        保存したファイルのパス
    """
    if archive_dir is None:
        archive_dir = PROJECT_ROOT / "executor_runs" / "runs"
    
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = archive_dir / f"run_{run.run_id}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(run.to_dict(), f, indent=2, ensure_ascii=False)
    
    return output_path


def run_dryrun_pre_submit(
    config: Optional[ExecutionConfig] = None,
    mode: str = "DRYRUN_PRE_SUBMIT",
    stop_before_submit: bool = True,
) -> RunLog:
    """
    Dry-run実行（PRE_SUBMITモード）
    
    Warning
    -------
    パスワードは絶対にログに保存しない（入力した事実だけ記録）
    """
    """
    Dry-run実行（PRE_SUBMITモード）
    
    Parameters
    ----------
    config : ExecutionConfig or None
        実行設定
    state_store : StateStore or None
        状態ストア
    mode : str
        実行モード（"DRYRUN_PRE_SUBMIT" | "LIVE_SUBMIT"）
    stop_before_submit : bool
        PRE_SUBMITで停止するか（デフォルト: True）
    
    Returns
    -------
    ExecutionRun
        実行ログ
    """
    if config is None:
        config = load_execution_config()
    
    # run_idを生成
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().isoformat()
    
    # RunLogを作成（latest_dateは後で設定）
    run = RunLog(
        run_id=run_id,
        created_at=created_at,
        latest_date=date.today(),  # 一時値、後で上書き
        mode=mode,
    )
    
    # RunLogの保存を必ず実行するため、try/finallyで包む
    try:
        # 0. 最新日を取得
        from executor.build_intent import read_latest_portfolio
        df_latest = read_latest_portfolio()
        latest_datetime = pd.to_datetime(df_latest["date"].iloc[0]).normalize()
        latest_date = latest_datetime.date()
        run.latest_date = latest_date
        
        # 1. core成果物からIntentを生成
        print(f"[{run_id}] Intent生成中...")
        print(f"  最新日: {latest_date}")
        
        order_intents, input_file_hash = build_order_intents_from_core(
            latest_date=latest_date,
            config=config,
        )
        run.inputs_hash = input_file_hash
        
        hedge_intents = build_hedge_intents_from_core(
            latest_date=latest_date,
            config=config,
        )
        
        run.order_intents = [intent.to_dict() for intent in order_intents]
        run.hedge_intents = [intent.to_dict() for intent in hedge_intents]
        
        # intent_hashを計算（冪等性確認用）
        # order_intentsを正規化してhash化（order_keyのみでソート）
        intent_keys = sorted([intent.order_key for intent in order_intents])
        intent_hash_str = "|".join(intent_keys)
        run.intent_hash = hashlib.sha256(intent_hash_str.encode("utf-8")).hexdigest()[:16]
        
        print(f"  OrderIntent: {len(order_intents)} 件")
        print(f"  HedgeIntent: {len(hedge_intents)} 件")
        print(f"  intent_hash: {run.intent_hash}")
        
        # 2. 事前チェック
        print(f"[{run_id}] 事前チェック中...")
        
        # 必要現金額・証拠金を計算
        required_cash = sum(
            intent.notional
            for intent in order_intents
            if intent.account == "cash" and intent.side == "buy"
        )
        required_margin = sum(
            intent.notional / config.leverage_ratio
            for intent in order_intents
            if intent.account == "cfd" and intent.side == "buy"
        )
        
        precheck_passed, precheck_results = run_prechecks(
            target_date=latest_date,
            required_cash=required_cash if required_cash > 0 else None,
            required_margin=required_margin if required_margin > 0 else None,
            available_cash=None,  # TODO: アダプターから取得
            available_margin=None,  # TODO: アダプターから取得
            cash_buffer=config.cash_buffer_jpy,
            margin_buffer_ratio=config.margin_buffer_ratio,
            connectivity_test_url=None,  # TODO: 設定から取得
        )
        
        # スナップショットにチェック結果を記録
        run.snapshots["precheck_results"] = [
            {
                "passed": result.passed,
                "reason": result.reason,
                "details": result.details,
            }
            for result in precheck_results
        ]
        
        # 各チェックの結果をスナップショットに個別記録
        for result in precheck_results:
            if result.reason == "trading_day":
                run.snapshots["trading_day_check"] = result.details
            elif result.reason.startswith("price_"):
                if "price_freshness" not in run.snapshots:
                    run.snapshots["price_freshness"] = {}
                run.snapshots["price_freshness"][result.reason] = result.details
            elif result.reason.startswith("cash_"):
                run.snapshots["cash_check"] = result.details
            elif result.reason.startswith("margin_"):
                run.snapshots["margin_check"] = result.details
            elif result.reason.startswith("connectivity_"):
                run.snapshots["connectivity_check"] = result.details
        
        if not precheck_passed:
            run.results["precheck_passed"] = False
            run.results["stop_reason"] = "PRECHECK_FAILED"
            run.results["errors"] = [
                {
                    "step": "precheck",
                    "reason": result.reason,
                    "details": result.details,
                }
                for result in precheck_results
                if not result.passed
            ]
            print(f"  事前チェック失敗: {run.results['stop_reason']}")
            return run
        
        print("  事前チェック通過")
        
        # 3. アダプター初期化・ログイン
        print(f"[{run_id}] アダプター初期化中...")
        cash_adapter = SBICashAdapter(config=_config_to_dict(config))
        cfd_adapter = SBICFDAdapter(config=_config_to_dict(config))
        
        # ログイン（TODO: 実装）
        # if not cash_adapter.login():
        #     run.stop_reason = "LOGIN_FAILED"
        #     return run
        
        # 4. 口座スナップショット取得
        print(f"[{run_id}] 口座スナップショット取得中...")
        # cash_snapshot = cash_adapter.get_account_snapshot()
        # cfd_snapshot = cfd_adapter.get_account_snapshot()
        # run.snapshots["cash_available"] = cash_snapshot.get("available_cash")
        # run.snapshots["margin_available"] = cfd_snapshot.get("available_margin")
        # run.snapshots["margin_maintenance_ratio"] = cfd_snapshot.get("maintenance_ratio")
        
        # 5. PRE_SUBMIT実行（アダプター経由）
        print(f"[{run_id}] PRE_SUBMIT実行中...")
        
        # 現物注文
        cash_intents = [intent for intent in order_intents if intent.account == "cash"]
        cash_result = None
        if cash_intents:
            cash_result = cash_adapter.execute_pre_submit(cash_intents)
            if not cash_result.success:
                run.results["stop_reason"] = cash_result.stop_reason or "CASH_ADAPTER_FAILED"
                run.results["errors"] = [
                    {
                        "step": "cash_adapter",
                        "error_message": cash_result.error_message,
                    }
                ]
                return run
        
        # CFD注文
        cfd_intents = [intent for intent in order_intents if intent.account == "cfd"]
        cfd_result = None
        if cfd_intents:
            cfd_result = cfd_adapter.execute_pre_submit(cfd_intents)
            if not cfd_result.success:
                run.results["stop_reason"] = cfd_result.stop_reason or "CFD_ADAPTER_FAILED"
                run.results["errors"] = [
                    {
                        "step": "cfd_adapter",
                        "error_message": cfd_result.error_message,
                    }
                ]
                return run
        
        # 6. PRE_SUBMIT結果をRunLogに記録
        if stop_before_submit:
            print(f"[{run_id}] PRE_SUBMIT停止（パスワード入力まで完了）")
            # パスワード入力の事実だけ記録（パスワード自体は絶対に保存しない）
            run.results["password_entered"] = True  # 入力した事実だけ
            
            # UI反映結果を統合
            ui_reflection_details = {}
            if cash_result:
                ui_reflection_details["cash"] = cash_result.ui_reflection_details
            if cfd_result:
                ui_reflection_details["cfd"] = cfd_result.ui_reflection_details
            
            run.results["ui_reflected"] = True
            run.results["ui_reflection_details"] = ui_reflection_details
            run.results["stop_reason"] = "STOP_BEFORE_SUBMIT"
        else:
            # LIVE_SUBMITモード（未実装）
            print(f"[{run_id}] LIVE_SUBMITモード（未実装）")
            run.results["stop_reason"] = "LIVE_SUBMIT_NOT_IMPLEMENTED"
        
        # 7. リソース解放
        cash_adapter.close()
        cfd_adapter.close()
        
        print(f"[{run_id}] 完了")
        
    except Exception as e:
        run.results["stop_reason"] = "ERROR"
        run.results["errors"] = [
            {
                "step": "execution",
                "error_type": type(e).__name__,
                "error_message": str(e),
            }
        ]
        print(f"[{run_id}] エラー: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # RunLogの保存を必ず実行（例外が発生しても残る）
        try:
            log_path = save_run_log(run)
            print(f"[{run_id}] 実行ログを保存: {log_path}")
            
            # OrderIntent CSV出力（任意だが推奨）
            try:
                csv_path = write_order_intent_csv(run)
                print(f"[{run_id}] OrderIntent CSV出力: {csv_path}")
            except Exception as csv_error:
                # CSV出力失敗は警告のみ（RunLogは必須、CSVは任意）
                print(f"[{run_id}] 警告: CSV出力に失敗: {csv_error}")
        
        except Exception as save_error:
            # ログ保存に失敗した場合も記録（可能な限り）
            print(f"[{run_id}] 警告: ログ保存に失敗: {save_error}")
            if "errors" not in run.results:
                run.results["errors"] = []
            run.results["errors"].append({
                "step": "save_log",
                "error_type": type(save_error).__name__,
                "error_message": str(save_error),
            })
    
    return run


def _config_to_dict(config: ExecutionConfig) -> Dict[str, Any]:
    """ExecutionConfigを辞書に変換（アダプター用）"""
    return {
        "aum": config.aum,
        "leverage_ratio": config.leverage_ratio,
        "margin_buffer_ratio": config.margin_buffer_ratio,
        "cash_buffer_jpy": config.cash_buffer_jpy,
    }


def main():
    """メイン実行"""
    import argparse
    
    parser = argparse.ArgumentParser(description="executor dry-run (PRE_SUBMIT)")
    parser.add_argument(
        "--mode",
        choices=["DRYRUN_PRE_SUBMIT", "LIVE_SUBMIT"],
        default="DRYRUN_PRE_SUBMIT",
        help="実行モード",
    )
    parser.add_argument(
        "--stop-before-submit",
        action="store_true",
        default=True,
        help="PRE_SUBMITで停止（デフォルト: True）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="設定ファイルパス（デフォルト: executor/config.json）",
    )
    
    args = parser.parse_args()
    
    # 設定読み込み
    if args.config is None:
        config = load_execution_config()
    else:
        config = load_execution_config(args.config)
    
    # 実行（ログ保存はrun_dryrun_pre_submit内で実行される）
    run = run_dryrun_pre_submit(
        config=config,
        mode=args.mode,
        stop_before_submit=args.stop_before_submit,
    )
    
    # 結果表示
    print(f"\n実行結果:")
    print(f"  run_id: {run.run_id}")
    print(f"  mode: {run.mode}")
    print(f"  stop_reason: {run.results.get('stop_reason')}")
    print(f"  order_intents: {len(run.order_intents)} 件")
    print(f"  hedge_intents: {len(run.hedge_intents)} 件")
    
    if run.results.get("errors"):
        print(f"  エラー: {len(run.results['errors'])} 件")
        for error in run.results["errors"]:
            print(f"    - {error.get('step')}: {error.get('error_message', error.get('reason'))}")


if __name__ == "__main__":
    main()

