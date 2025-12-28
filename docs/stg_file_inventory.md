# stg整理後のファイル一覧

**更新日**: 2025-12-28  
**目的**: stg整理完了後のcore/analysisファイル構成を記録

---

## scripts/core/（実運営に必要な最小構成）

### 1. universe_builder.py
- **目的**: ユニバース構築（流動性トップ銘柄の選定）
- **入力**: `configs/universe.yml`, JPX上場銘柄リスト, 価格データ
- **出力**: `data/intermediate/universe/YYYYMMDD_universe.parquet`, `latest_universe.parquet`
- **実運営**: ✅ 必要（ユニバース定義の生成）

### 2. download_prices.py
- **目的**: ユニバース銘柄の株価をYahoo Financeから一括ダウンロード
- **入力**: ユニバースファイル（.parquet）
- **出力**: `data/raw/prices/prices_{TICKER}.csv`
- **実運営**: ✅ 必要（価格データ取得）
- **【⑤ 祝日・価格未更新日の挙動（予防線）】**:
  - 取得不能時は例外をキャッチして警告を出力し、次の銘柄に進む（処理は継続）
  - 営業日カレンダーによる事前判定は行わない（Yahoo Finance側のデータ有無に依存）
  - 営業日カレンダー実装は不要（予防線のみ）

### 3. build_features.py
- **目的**: 特徴量構築（モメンタム・ボラティリティ等の特徴量を計算）
- **入力**: 価格データ（`data/raw/prices/`）
- **出力**: `data/processed/daily_feature_scores.parquet`
- **実運営**: ✅ 必要（特徴量生成）
- **【① TOPIX依存の可視化】TOPIX（日次指数リターン）を参照**:
  - データ欠損時は `mkt_ret_1d = 0.0` でフォールバック（警告を出力）
  - 無言スルー禁止：データが見つからない場合は警告を出力
- **【② run_scoring 二重実行の回避（設計確定）】:
  - `build_features.py` 内で `compute_scores_all` を呼び出してスコアリングを実行
  - `run_scoring.py` は別途実行しない（二重実行を回避）
  - スコアリングは `build_features.py` 内で完結する

### 4. run_scoring.py
- **目的**: スコアリング実行（CLIエントリポイント）
- **入力**: `configs/scoring.yml`
- **出力**: `data/intermediate/scoring/latest_scores.parquet`
- **実運営**: ⚠️ オプション（`build_features.py`内でスコアリングが実行されるため、通常は不要）
- **【② run_scoring 二重実行の回避（設計確定）】:
  - `build_features.py` 内で `compute_scores_all` を呼び出してスコアリングを実行するため、
    `run_scoring.py` を別途実行すると二重実行となる
  - coreパイプライン（`run_equity01_core.ps1`）では `run_scoring.py` を実行しない
  - 手動でスコアリングのみ実行したい場合のみ使用

### 5. scoring_engine.py
- **目的**: スコアリングエンジン（feature_score → size bucket別Z-score → ポートフォリオ候補生成）
- **主要関数**: `ScoringEngineConfig`, `build_daily_portfolio`, `run_from_config`
- **実運営**: ✅ 必要（スコアリングロジック）

### 6. build_portfolio.py
- **目的**: ポートフォリオ構築（運用終点生成）
- **入力**: `data/processed/daily_feature_scores.parquet`
- **出力**: `data/processed/daily_portfolio_guarded.parquet`（運用終点、Executionが読む正本）
- **実運営**: ✅ 必要（運用終点生成）
- **【③ 最重要】latest解釈の固定（契約レベル）**: 
  - date列をdatetimeに正規化（timezoneなし）してから保存
  - date列で昇順ソートしてから保存
  - **実運用では `daily_portfolio_guarded.parquet` の `date` 列の `max(date)` の行のみを使用する**
  - latest専用ファイル作成・完了フラグ・営業日判定は不要

**実行順序**:
```bash
# 1. ユニバース構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格データ取得
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet

# 3. 特徴量構築（内部でスコアリングも実行される）
python scripts/core/build_features.py

# 4. ポートフォリオ構築（運用終点生成）
python scripts/core/build_portfolio.py
```

**注意**: `run_scoring.py` は `build_features.py` 内でスコアリングが実行されるため、通常は実行不要です。

**【④ 途中生成物の扱い（明示のみ）】**:
- 途中失敗時に生成物が残る可能性があるが、
  Executionは `daily_portfolio_guarded.parquet` の `max(date)` 行のみを使用するため問題ない

---

## scripts/analysis/（weights型ファイル生成、研究用）

### 1. generate_variant_weights.py
- **目的**: variant別/horizon別の日次weightsを生成
- **入力**: `data/processed/daily_feature_scores.parquet`（core生成物）
- **出力**: `data/processed/weights/h{H}_{ladder}_{variant}.parquet`（date, symbol, weight）
- **仕様**:
  - nonladder: horizon間隔でリバランスし、そのweightsをhorizon日ホールド（複製）
  - ladder: 毎日weightsを生成し、直近h本の平均を使用（全営業日のweightsを生成）
- **用途**: 研究用（weights型ファイル生成）

### 2. build_cross4_target_weights.py
- **目的**: cross4 target weightsを生成（Variant合成 + Horizon合成）
- **入力**: `data/processed/weights/h{H}_{ladder}_{variant}.parquet`（generate_variant_weights.pyの出力）
- **出力**: 
  - `data/processed/weights/cross4_target_weights.parquet`（全期間）
  - `data/processed/weights/cross4_target_weights_latest.parquet`（最新日のみ）
- **合成ロジック**:
  - Variant合成: `w_cross4_h = 0.75 * w_rank_only_h + 0.25 * w_zdownvol_h`
  - Horizon合成: `w_cross4 = Σ_h (horizon_weight[h] * w_cross4_h)`
- **用途**: 研究用（weights型ファイル生成）

### 3. build_cross4_target_weights_with_stop.py
- **目的**: STOP付cross4 target weightsを生成
- **入力**: `data/processed/weights/cross4_target_weights.parquet`（STOP無しのcross4 weights）
- **出力**: `data/processed/weights/cross4_target_weights_{strategy}_w{window}.parquet`
  - strategy: stop0, planA, planB
  - window: 60, 120
- **STOPロジック**:
  - STOP条件: `(alphaのローリング合計 < 0) & (TOPIXのローリング合計 < 0)`
  - STOP0: STOP期間中はweights=0（完全キャッシュ）
  - Plan A: STOP期間中はweightsを維持
  - Plan B: STOP期間中はweightsを0.5倍
- **用途**: 研究用（weights型ファイル生成）

### 4. backtest_from_weights.py
- **目的**: weightsからreturnsを計算するバックテスト
- **入力**: `data/processed/weights/cross4_target_weights.parquet`（date, symbol, weight）
- **出力**: `data/processed/weights_bt/cross4_from_weights.parquet`（trade_date, port_ret_cc, cumulativeなど）
- **計算ロジック**: `w[t-1] * r[t]`（正しい定義、look-aheadバイアスなし）
- **用途**: 研究用（weights型ファイルからreturns計算）

### 5. backtest_from_weights_with_stop.py
- **目的**: STOP付cross4 weightsからreturnsを計算するバックテスト
- **入力**: `data/processed/weights/cross4_target_weights_{strategy}_w{window}.parquet`
- **出力**: `data/processed/weights_bt/cross4_from_weights_{strategy}_w{window}.parquet`
- **計算ロジック**: `w[t-1] * r[t]`（STOP条件を適用したweightsを使用）
- **用途**: 研究用（weights型ファイルからreturns計算）

**実行順序（研究用）**:
```bash
# ① variant別/horizon別のweightsを生成
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 1 --ladder nonladder
python scripts/analysis/generate_variant_weights.py --variant rank --horizon 60 --ladder ladder
# ... (他のvariant/horizonの組み合わせ)

# ② cross4 target weightsを生成
python scripts/analysis/build_cross4_target_weights.py

# ③ STOP付cross4 target weightsを生成（オプション）
python scripts/analysis/build_cross4_target_weights_with_stop.py --strategy stop0 --window 60

# ④ weights→returnsを計算
python scripts/analysis/backtest_from_weights.py
python scripts/analysis/backtest_from_weights_with_stop.py --strategy stop0 --window 60
```

---

## deprecated/2025Q4_pre_weights_fix/に移動したファイル

以下のファイルはeval型（評価・分析用）、旧パイプライン由来、または未完成のためdeprecatedに移動：

### scripts/core/から移動
- `run_equity01_eval.py` - 統合評価スクリプト（port_ret_cc使用）
- `calc_alpha_beta.py` - ペーパートレード結果に相対αを後乗せ（port_ret_cc使用）
- `build_dynamic_portfolio.py` - 動的ウェイトポートフォリオ構築（ensemble系に依存）
- `build_regime_hmm.py` - HMMレジームクラスタリング（horizon_ensemble_variant_cross4.parquetに依存）
- `event_guard.py` - イベントガード（ロジック構築未完成）

### scripts/analysis/から移動
- ensemble系（12ファイル）
- run_all系（7ファイル）
- debug/verify/compare/audit/analyze系（15ファイル以上）
- eval系（2ファイル）
- その他分析・可視化スクリプト（約15ファイル）

詳細は `deprecated/2025Q4_pre_weights_fix/README.md` を参照。

---

## 実行確認

### stg sanity check
```bash
python scripts/stg_sanity_check.py
```

このコマンドで以下を確認：
1. Core 5ファイル（analysis配下）が正常にimportできること
2. 主要関数が存在すること
3. 生成物パスが存在すること（あれば）

---

## 運用終点

実運営で使用する運用終点は：
- **`data/processed/daily_portfolio_guarded.parquet`**
  - `weight` 列を含み、実運用で直接使用可能
  - 最新日（latest date）の行を読み込んで使用
  - `scripts/core/build_portfolio.py` で生成

weights型ファイル（`data/processed/weights/`配下）は研究用であり、実運営では使用しない。

---

## 運用上の注意事項

### universe_builderのyfinance取得失敗時の挙動
- **現在の設定**: A案（堅牢）を採用
  - yfinance取得失敗時は、前回の`latest_universe.parquet`を使用して継続
  - ログに`[ERROR]`を記録し、`[FALLBACK]`として前回データを使用
  - 運用は継続されるが、ログで確認可能
- **代替案**: B案（品質）
  - yfinance取得失敗時は`ExitCode!=0`で停止（その日は運用しない）
  - より厳格だが、データ品質を優先

### Windowsタスクスケジューラの運用設定
- **実行時間帯**: 営業日の朝（例：平日 8:00）
- **タイムアウト**: 2時間（120分）
- **失敗時の再実行**: 基本なし（自動リトライなし）
- **ログ保管期間**: 30日（自動ローテーション）

