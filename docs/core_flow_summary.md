# coreフロー要約（始点→終点）

## 運用フロー（core完結）

始点（raw/config）→終点（運用が読む1ファイル）までの正規実行順序：

### 実行順序

1. **universe_builder.py** - ユニバース構築
   - 入力: `configs/universe.yml`, `data/raw/jpx_listings/*.csv`, `data/raw/prices/*.csv`
   - 出力: `data/intermediate/universe/latest_universe.parquet`

2. **download_prices.py** - 価格データ取得
   - 入力: `data/intermediate/universe/latest_universe.parquet`
   - 出力: `data/raw/prices/prices_{ticker}.csv` (または `scripts/tools/fetch_prices.py` で `data/raw/equities/{ticker}.parquet`)

3. **build_index_tpx_daily.py** - TOPIXデータ構築
   - 入力: `data/raw/prices/*.csv`
   - 出力: `data/processed/index_tpx_daily.parquet`

4. **build_features.py** - 特徴量構築
   - 入力: `data/raw/equities/*.parquet`, `data/processed/index_tpx_daily.parquet`
   - 出力: `data/processed/daily_feature_scores.parquet`

5. **build_portfolio.py** - ポートフォリオ構築
   - 入力: `data/processed/daily_feature_scores.parquet`, `data/events/calendar.csv`, `data/events/earnings.csv`
   - 出力: **`data/processed/daily_portfolio_guarded.parquet`** ← **運用終点（Executionが読む正本）**

### 運用終点

**`data/processed/daily_portfolio_guarded.parquet`**

- 生成元: `scripts/core/build_portfolio.py:63`
- 内容: `weight` 列を含み、実運用で直接使用可能
- 使用方法: Executionはこのファイルの最新日（latest date）の行を読み込む

---

## 評価フロー（オプション、運用終点ではない）

6. **run_equity01_eval.py** - 評価パイプライン（評価・分析用）
   - 入力: `data/processed/daily_portfolio_guarded.parquet`, `data/processed/index_tpx_daily.parquet`
   - 出力: `data/processed/paper_trade_with_alpha_beta.parquet`, `data/processed/rolling_relative_alpha.parquet`
   - **注意**: 評価・分析用であり、運用終点ではない

---

## core→analysis依存ゼロの確認

**確認結果:**
```bash
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
# 結果: 0件
```

**結論:**
- coreからanalysisへの依存は存在しない ✅
- analysisはcore生成物（parquet）を読むだけ（書き戻し禁止）

---

## 詳細

- `docs/core_flow_table.md` - 実行順序と入出力の詳細（証拠行リンク付き）
- `docs/pipeline_graph.md` - パイプライン依存図（Mermaid）
- `docs/target_weights_analysis.md` - 運用終点の分析

