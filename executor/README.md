# executor: Intent-based Execution Module

## 概要

executorは、core（数理・αβ・STOP）の成果物を受け取り、実運用で注文を実行するモジュールです。

**executorはprod正本として設計されています。execution/はlegacy（参照専用・凍結）です。**

coreは完全一致検証を通過して確定しているため、executorを正本として実行系を固めます。

## 設計原則

- **Intent-based**: 計算（core）と実行（executor）を分離
- **Fail-safe**: 休日・通信・余力・価格stale時は「止まる」
- **Idempotent**: 同日再実行 → 同一 Intent / 同一結果
- **Audit-first**: 何を判断し、なぜ止めたかがログで追える

## ディレクトリ構造

```
executor/
├── __init__.py
├── models.py              # OrderIntent / HedgeIntent / ExecutionRun
├── precheck.py            # 事前チェック（休日・余力・価格鮮度・通信）
├── build_intent.py        # core成果物からIntent生成
├── dryrun.py              # DRYRUN_PRE_SUBMITモード実装
├── config.json            # 実行設定
├── adapters/              # 証券会社アダプター
│   ├── __init__.py
│   ├── sbi_cash.py        # SBI証券 現物取引
│   └── sbi_cfd.py         # SBI証券 CFD取引
└── archives/              # 実行ログ（.gitignore）
    └── runs/              # run_{run_id}.json
```

## Intentスキーマ

### OrderIntent

```python
OrderIntent(
    date: date,
    account: "cash" | "cfd",
    symbol: str,
    side: "buy" | "sell",
    qty: int,  # executor側で確定
    price_ref: "last" | "close",
    reason: "rebalance" | "hedge" | "stop",
    constraints: Dict[str, Any],
    notional: float,
    ...
)
```

### HedgeIntent

```python
HedgeIntent(
    date: date,
    hedge_type: "inverseETF" | "CFD",
    ref_beta: float,  # t-1時点のβ
    target_notional: float,
    hedge_ratio: float,
    ...
)
```

## 実行モード

- **DRYRUN_PRE_SUBMIT**: 注文画面まで進み、最終クリックだけ実行しない（stg終了ゲート）
- **LIVE_SUBMIT**: 実際に発注する（prd用、未実装）

## 使用方法

### Dry-run実行（PRE_SUBMITモード）

```bash
python executor/dryrun.py --mode DRYRUN_PRE_SUBMIT
```

### 設定

`executor/config.json` を編集：

```json
{
  "mode": "DRYRUN_PRE_SUBMIT",
  "stop_before_submit": true,
  "aum": 100000000.0,
  ...
}
```

## ログ設計

1 run = 1 ファイル: `executor/archives/runs/run_{run_id}.json`

内容:
- `latest_date` / `run_at` / `mode`
- 入力ファイルhash（再現性確保）
- 各Intent（symbol / side / qty / notional）
- 余力スナップショット（現物 / CFD / 維持率）
- UI反映結果（成功/失敗）
- 停止理由：`STOP_BEFORE_SUBMIT`

**注意**: パスワードは絶対にログに残さない

## stg終了ゲート（判断基準）

- **A. 実行整合**: 同日再実行 → 同一 Intent / 同一 PRE_SUBMIT（冪等）
- **B. 余力・証拠金**: 現物/CFDともにbufferを割らない
- **C. 実効コスト**: 回転率 / 総 notional / 想定手数料・スリッページをログ化

## 実装状況

- ✅ `models.py`: Intentスキーマ定義
- ✅ `precheck.py`: 事前チェック実装
- ✅ `build_intent.py`: Intent生成（core成果物から、execution/から完全独立）
- ✅ `dryrun.py`: DRYRUN_PRE_SUBMITモード実装
- ✅ `adapters/`: stub実装完了（PRE_SUBMITを返す）
- ✅ ログ設計: `executor_runs/runs/run_{run_id}.json`

## execution/との関係

**execution/はlegacy（参照専用・凍結）です。**

- execution/は過去の試行・暫定的な実装
- executor/は現在と未来の正本
- 以後の新機能はexecutor/のみに実装
- execution/への依存は完全に排除済み

## 次のステップ

1. SBIアダプターのSelenium実装
2. パスワード管理（secrets/）
3. スクリーンショット・DOM dump保存
4. LIVE_SUBMITモード実装（prd用）

