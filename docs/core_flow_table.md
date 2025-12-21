# scripts/core/ 実行フロー表

## 概要

`scripts/core/run_equity01_eval.py` を実行した際の、各ステップでの入出力parquetと呼び出しスクリプトをまとめます。

---

## 実行フロー（run_equity01_eval.py）

### STEP 1: build_index_tpx_daily

**呼び出し:**
- `scripts.tools.build_index_tpx_daily.main()`

**入力:**
- `data/raw/prices/*.csv` (TOPIXデータ: ^TOPX または 1306.T)

**出力:**
- `data/processed/index_tpx_daily.parquet` (TOPIX日次リターン)

**生成元スクリプト:**
- `scripts/tools/build_index_tpx_daily.py`

**証拠行（コード位置）:**
- 出力保存: [`scripts/tools/build_index_tpx_daily.py:84`](scripts/tools/build_index_tpx_daily.py#L84) (`df_output.to_parquet(out, index=False)`)

---

### STEP 2: calc_alpha_beta（評価用）

**呼び出し:**
- `scripts.core.calc_alpha_beta.main()`

**内部処理:**
1. `tools.paper_trade.run_paper_trade()` を呼び出し
   - **入力**: `data/processed/daily_portfolio_guarded.parquet` (ポートフォリオ)
   - **入力**: `data/raw/equities/*.parquet` (価格データ)
   - **出力**: `df_daily` (ペーパートレード日次結果)
2. `calc_alpha_beta.load_tpx_returns()` でTOPIXデータを読み込み
   - **入力**: `data/processed/index_tpx_daily.parquet`
3. `calc_alpha_beta.merge_portfolio_with_tpx()` でマージ
4. 相対αを計算して保存

**入力:**
- `data/processed/daily_portfolio_guarded.parquet` (STEP 2の前提として必要)
- `data/processed/index_tpx_daily.parquet` (STEP 1の出力)

**出力:**
- `data/processed/paper_trade_with_alpha_beta.parquet` (ペーパートレード結果 + 相対α)
  - **評価・分析用の出力（運用終点ではない）**

**生成元スクリプト:**
- `scripts/core/calc_alpha_beta.py`
- `scripts/tools/paper_trade.py` (内部呼び出し)

**証拠行（コード位置）:**
- TOPIX入力読み込み: [`scripts/core/calc_alpha_beta.py:27`](scripts/core/calc_alpha_beta.py#L27) (`df = pd.read_parquet(path)`)
- TOPIX入力パス: [`scripts/core/calc_alpha_beta.py:25`](scripts/core/calc_alpha_beta.py#L25) (`path: str = "data/processed/index_tpx_daily.parquet"`)
- ポートフォリオ入力（paper_trade経由）: [`scripts/tools/paper_trade.py:127`](scripts/tools/paper_trade.py#L127) (`df_port = pd.read_parquet(cfg.portfolio_path)`)
- 出力保存: [`scripts/core/calc_alpha_beta.py:165`](scripts/core/calc_alpha_beta.py#L165) (`df.to_parquet(out, index=False)`) ← **評価用**
- 出力パス: [`scripts/core/calc_alpha_beta.py:163`](scripts/core/calc_alpha_beta.py#L163) (`out = Path("data/processed/paper_trade_with_alpha_beta.parquet")`)

**注意:**
- `daily_portfolio_guarded.parquet` は `build_portfolio.py` で生成されるが、`run_equity01_eval.py` からは直接呼び出されていない
- 実行順序としては `build_portfolio.py` → `run_equity01_eval.py` が前提
- **このステップは評価用であり、運用終点ではない**

---

### STEP 3: rolling_relative_alpha（評価用）

**内部処理:**
- `compute_rolling_relative_alpha()` 関数を実行

**入力:**
- `data/processed/paper_trade_with_alpha_beta.parquet` (STEP 2の出力)

**出力:**
- `data/processed/rolling_relative_alpha.parquet` (10/20/60/120日ローリング相対α)
  - **評価・分析用の出力（運用終点ではない）**

**生成元スクリプト:**
- `scripts/core/run_equity01_eval.py` (内部関数)

**証拠行（コード位置）:**
- 入力読み込み: [`scripts/core/run_equity01_eval.py:125`](scripts/core/run_equity01_eval.py#L125) (`df_alpha = pd.read_parquet(src)`)
- 入力パス: [`scripts/core/run_equity01_eval.py:123`](scripts/core/run_equity01_eval.py#L123) (`src = Path("data/processed/paper_trade_with_alpha_beta.parquet")`)
- 出力保存: [`scripts/core/run_equity01_eval.py:69`](scripts/core/run_equity01_eval.py#L69) (`out.to_parquet(out_path, index=False)`) ← **評価用**
- 出力パス: [`scripts/core/run_equity01_eval.py:67`](scripts/core/run_equity01_eval.py#L67) (`out_path = Path(f"data/processed/rolling_relative_alpha_{label}.parquet")`)

**注意:**
- **このステップは評価用であり、運用終点ではない**

---

## 前提条件（run_equity01_eval.py の実行前に必要）

### 1. universe_builder.py

**実行:**
```bash
python scripts/core/universe_builder.py --config configs/universe.yml
```

**入力:**
- `configs/universe.yml` (設定ファイル)
- `data/raw/jpx_listings/*.csv` (JPX上場銘柄リスト)
- `data/raw/prices/*.csv` または `data/raw/equities/*.parquet` (価格データ)

**出力:**
- `data/intermediate/universe/{YYYYMMDD}_universe.parquet` (日次ユニバース)
- `data/intermediate/universe/latest_universe.parquet` (最新ユニバースへのシンボリックリンクまたはコピー)

**生成元スクリプト:**
- `scripts/core/universe_builder.py`

**証拠行（コード位置）:**
- 入力読み込み: [`scripts/core/universe_builder.py:61`](scripts/core/universe_builder.py#L61) (`pd.read_parquet(p_parq)`)
- 入力読み込み: [`scripts/core/universe_builder.py:69`](scripts/core/universe_builder.py#L69) (`pd.read_parquet(p) if p.suffix==".parquet"`)
- 出力保存: [`scripts/core/universe_builder.py:229`](scripts/core/universe_builder.py#L229) (`uni.to_parquet(out_path, index=False)`)

---

### 2. download_prices.py

**実行:**
```bash
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet
```

**入力:**
- `data/intermediate/universe/latest_universe.parquet` (ユニバース)

**出力:**
- `data/raw/prices/prices_{ticker}.csv` (銘柄別価格データ、CSV形式)

**生成元スクリプト:**
- `scripts/core/download_prices.py`

**証拠行（コード位置）:**
- 入力読み込み: [`scripts/core/download_prices.py:30`](scripts/core/download_prices.py#L30) (`pd.read_parquet(universe_path)`)
- デフォルトパス: [`scripts/core/download_prices.py:44`](scripts/core/download_prices.py#L44) (`default="data/intermediate/universe/latest_universe.parquet"`)
- 出力保存: [`scripts/core/download_prices.py:180`](scripts/core/download_prices.py#L180) (`df.to_csv(out_path, index=False)`)
- 出力パス: [`scripts/core/download_prices.py:163`](scripts/core/download_prices.py#L163) (`out_path = outdir / f"prices_{ticker}.csv"`)

**注意:**
- `download_prices.py` は CSV 形式で出力します
- `build_features.py` は `data_loader.py` 経由で `data/raw/equities/*.parquet` も読み込めます
- または `scripts/tools/fetch_prices.py` を使用して parquet 形式で出力することも可能（非推奨）
  - `scripts/tools/fetch_prices.py:116` (`data.to_parquet(out_path, index=False)`) → `data/raw/equities/{ticker}.parquet`

---

### 3. build_features.py

**実行:**
```bash
python scripts/core/build_features.py
```

**入力:**
- `data/raw/equities/*.parquet` (銘柄別価格データ) - `scripts/tools/data_loader.py` 経由で読み込み
- `data/processed/index_tpx_daily.parquet` (TOPIXデータ、オプション)

**出力:**
- `data/processed/daily_feature_scores.parquet` (特徴量 + スコア)

**生成元スクリプト:**
- `scripts/core/build_features.py`
- `scripts/tools/feature_builder.py` (内部使用)
- `scripts/core/scoring_engine.py` (内部使用: `compute_scores_all`)

**証拠行（コード位置）:**
- TOPIX入力読み込み: [`scripts/core/build_features.py:71`](scripts/core/build_features.py#L71) (`df_tpx = pd.read_parquet(tpx_path)`)
- TOPIX入力パス: [`scripts/core/build_features.py:69`](scripts/core/build_features.py#L69) (`tpx_path = Path("data/processed/index_tpx_daily.parquet")`)
- 出力保存: [`scripts/core/build_features.py:170`](scripts/core/build_features.py#L170) (`df_featured.to_parquet(out_path, index=False)`)
- 出力パス: [`scripts/core/build_features.py:168`](scripts/core/build_features.py#L168) (`out_path = Path("data/processed/daily_feature_scores.parquet")`)

---

### 4. run_scoring.py

**実行:**
```bash
python scripts/core/run_scoring.py --config configs/scoring.yml
```

**入力:**
- `configs/scoring.yml` (設定ファイル)
- `data/processed/daily_feature_scores.parquet` (特徴量データ、設定ファイルで指定)

**出力:**
- `data/intermediate/scoring/{YYYYMMDD}_scores.parquet` (日次スコア)
- `data/intermediate/scoring/latest_scores.parquet` (最新スコアへのシンボリックリンクまたはコピー)

**生成元スクリプト:**
- `scripts/core/run_scoring.py`
- `scripts/core/scoring_engine.py` (内部使用: `run_from_config`)

**注意:**
- `build_features.py` で既にスコアが計算されている場合、このステップは省略可能

---

### 5. build_portfolio.py

**実行:**
```bash
python scripts/core/build_portfolio.py
```

**入力:**
- `data/processed/daily_feature_scores.parquet` (特徴量 + スコア)
- `data/events/calendar.csv` (イベントカレンダー)
- `data/events/earnings.csv` (決算カレンダー)

**出力:**
- `data/processed/daily_portfolio_guarded.parquet` (ポートフォリオ + EventGuard適用)
  - **★ 運用終点（Executionが読む正本）**
  - `weight` 列を含み、実運用で直接使用可能

**生成元スクリプト:**
- `scripts/core/build_portfolio.py`
- `scripts/core/scoring_engine.py` (内部使用: `build_daily_portfolio`)
- `scripts/core/event_guard.py` (内部使用: EventGuard)

**証拠行（コード位置）:**
- 入力読み込み: [`scripts/core/build_portfolio.py:20`](scripts/core/build_portfolio.py#L20) (`df_features = pd.read_parquet(feat_path)`)
- 入力パス: [`scripts/core/build_portfolio.py:19`](scripts/core/build_portfolio.py#L19) (`feat_path = Path("data/processed/daily_feature_scores.parquet")`)
- 出力保存: [`scripts/core/build_portfolio.py:63`](scripts/core/build_portfolio.py#L63) (`df_port.to_parquet(out_path, index=False)`) ← **運用終点生成**
- 出力パス: [`scripts/core/build_portfolio.py:61`](scripts/core/build_portfolio.py#L61) (`out_path = Path("data/processed/daily_portfolio_guarded.parquet")`)

---

## 完全な実行順序（coreフロー正規実行順序）

### 運用フロー（core完結）

```bash
# 1. ユニバース構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格データ取得
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet

# 3. TOPIXデータ構築
python scripts/tools/build_index_tpx_daily.py

# 4. 特徴量構築
python scripts/core/build_features.py

# 5. スコアリング（オプション、build_features.py で既に計算されている場合は省略可）
python scripts/core/run_scoring.py --config configs/scoring.yml

# 6. ポートフォリオ構築（運用終点生成）
python scripts/core/build_portfolio.py
# → 出力: data/processed/daily_portfolio_guarded.parquet（Executionが読む正本）
```

### 評価フロー（オプション）

```bash
# 7. 評価パイプライン実行（評価・分析用）
python scripts/core/run_equity01_eval.py
# → 出力: data/processed/paper_trade_with_alpha_beta.parquet（評価用）
# → 出力: data/processed/rolling_relative_alpha.parquet（評価用）
```

**注意:**
- ステップ1-6が運用フロー（core完結）
- ステップ7は評価・分析用であり、運用終点ではない
- 運用終点はステップ6で生成される `daily_portfolio_guarded.parquet`

---

## 運用終点について

### 運用終点（Executionが読む正本）

**`data/processed/daily_portfolio_guarded.parquet`** が coreフローの運用終点です。

**生成元:**
- `scripts/core/build_portfolio.py`

**証拠行:**
- 出力保存: [`scripts/core/build_portfolio.py:63`](scripts/core/build_portfolio.py#L63) (`df_port.to_parquet(out_path, index=False)`)
- 出力パス: [`scripts/core/build_portfolio.py:61`](scripts/core/build_portfolio.py#L61) (`out_path = Path("data/processed/daily_portfolio_guarded.parquet")`)

**内容:**
- `date` / `trading_date` / `decision_date` - 日付情報
- `symbol` - 銘柄コード
- `size_bucket` - サイズバケット（Large/Mid/Small）
- `feature_score` - 特徴量スコア
- `z_score_bucket` - バケット内Z-score
- `selected` - 選定フラグ
- **`weight`** - **ウェイト（実運用で使用）**
- `hedge_ratio` - ヘッジ比率
- `inverse_symbol` - インバースETFシンボル

**使用方法:**
- Executionはこのファイルの最新日（latest date）の行を読み込む
- `weight` 列を使用して実運用でのウェイト配分を決定

---

### 評価・分析用の出力（運用終点ではない）

以下のファイルは評価・分析用であり、運用終点ではありません：

1. **`data/processed/paper_trade_with_alpha_beta.parquet`**
   - ペーパートレード結果 + 相対α
   - 生成元: `scripts/core/calc_alpha_beta.py`（評価用）

2. **`data/processed/rolling_relative_alpha.parquet`**
   - ローリング相対α（10/20/60/120日）
   - 生成元: `scripts/core/run_equity01_eval.py`（評価用）

**注意:**
- `run_equity01_eval.py` は「評価」であって終点ではない
- 運用終点は `build_portfolio.py` で生成される `daily_portfolio_guarded.parquet`

---

### target_weights_latest.parquet について

**現状:**
- `target_weights_latest.parquet` というファイルは存在しません
- `daily_portfolio_guarded.parquet` を運用終点として使用します（Option A採用）

**採用方針:**
- **Option A（採用）**: `daily_portfolio_guarded.parquet` をそのまま運用終点として使用
  - 追加のスクリプト不要
  - 既存のフローを変更する必要がない
  - `weight` 列が含まれており実運用で使用可能

**詳細:**
- `docs/target_weights_analysis.md` を参照

---

## cross4 と STOP の扱い（analysis固定）

### cross4 について

**生成:**
- `scripts/analysis/ensemble_variant_cross4.py` で生成
- **出力**: `data/processed/horizon_ensemble_variant_cross4.parquet`

**使用:**
- `scripts/analysis/eval_stop_regimes.py` で使用
- `scripts/analysis/eval_stop_regimes_robustness.py` で使用
- `scripts/core/build_regime_hmm.py:58` で使用（KEEP_STG_ANALYSIS、coreフローとは別系統）

**位置づけ:**
- **KEEP_STG_ANALYSIS** - analysis側の検証・評価用アンサンブル
- coreフロー（運用終点）とは別系統（analysis側）
- coreフローは cross4 を使用しない

### STOP について

**評価・検証:**
- `scripts/analysis/eval_stop_regimes.py` で評価・検証
- `scripts/analysis/eval_stop_regimes_robustness.py` でロバストネステスト

**レジームHMM構築:**
- `scripts/core/build_regime_hmm.py:345` でレジームHMM構築（KEEP_STG_ANALYSIS、coreフローとは別系統）
  - **入力**: `horizon_ensemble_variant_cross4.parquet` ([`build_regime_hmm.py:58`](scripts/core/build_regime_hmm.py#L58))
  - **出力**: `data/processed/regime_labels.parquet` ([`build_regime_hmm.py:345`](scripts/core/build_regime_hmm.py#L345))

**位置づけ:**
- **KEEP_STG_ANALYSIS** - analysis側の検証・評価用
- coreフロー（運用終点）とは別系統（analysis側）
- coreフローは STOP を使用しない

**注意:**
- `scripts/core/build_regime_hmm.py` は `scripts/core/` に配置されているが、cross4を使用しているため **KEEP_STG_ANALYSIS** として扱う
- 将来的に `scripts/analysis/` に移動することも検討可能（ただし、importパスの修正が必要）

### coreフローとの関係

**結論:**
- cross4 と STOP は coreフロー（運用終点）とは別系統（analysis側）のため、coreフロー内での合流点は存在しません
- coreフローの終点（`daily_portfolio_guarded.parquet`）は、cross4/STOP とは独立して生成されます
- **core→analysis依存ゼロ** が保証されている（0件確認）

**詳細:**
- `docs/cross4_stop_analysis_fixed.md` を参照

