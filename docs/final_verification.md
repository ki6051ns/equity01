# 最終検証結果

## 実施日

2025-01-XX

---

## 検証項目

### 1. 始点→終点の運用フローが1本に確定（core完結）

✅ **完了**

- `docs/core_flow_table.md` に正規実行順序を記録
- 運用終点: `data/processed/daily_portfolio_guarded.parquet` を明記
- `run_equity01_eval.py` は「評価」であって終点ではないことを明記

**証拠:**
- `docs/core_flow_table.md` - 「運用終点について」セクションを参照
- `docs/core_flow_summary.md` - 要約版を作成

---

### 2. 各スクリプトの入出力parquetが書かれている行をコード位置で裏取り

✅ **完了**

各スクリプトに証拠行リンクを追加：

- **universe_builder.py**:
  - 入力: `scripts/core/universe_builder.py:61`, `:69`
  - 出力: `scripts/core/universe_builder.py:229`

- **download_prices.py**:
  - 入力: `scripts/core/download_prices.py:30`
  - 出力: `scripts/core/download_prices.py:180`

- **build_index_tpx_daily.py**:
  - 出力: `scripts/tools/build_index_tpx_daily.py:84`

- **build_features.py**:
  - 入力: `scripts/core/build_features.py:71`
  - 出力: `scripts/core/build_features.py:170`

- **build_portfolio.py**:
  - 入力: `scripts/core/build_portfolio.py:20`
  - 出力: `scripts/core/build_portfolio.py:63` ← **運用終点**

- **calc_alpha_beta.py**:
  - 入力: `scripts/core/calc_alpha_beta.py:27`, `scripts/tools/paper_trade.py:127`
  - 出力: `scripts/core/calc_alpha_beta.py:165`

- **run_equity01_eval.py**:
  - 入力: `scripts/core/run_equity01_eval.py:125`
  - 出力: `scripts/core/run_equity01_eval.py:69`

**証拠:**
- `docs/core_flow_table.md` - 各ステップに「証拠行（コード位置）」セクションを追加

---

### 3. 終点ファイル名を運用向けに明確化（Option A採用）

✅ **完了（Option A採用）**

- 終点: `data/processed/daily_portfolio_guarded.parquet` のまま
- Executionはこのファイルの最新日（latest date）の行を読む
- READMEとdocsに「終点＝daily_portfolio_guarded」を明記

**証拠:**
- `README.md` - 「運用終点」セクションを追加
- `docs/core_flow_table.md` - 「運用終点について」セクションを更新
- `docs/target_weights_analysis.md` - Option Aを採用

---

### 4. core→analysis依存ゼロを自動チェックしてレポート

✅ **完了**

**確認コマンド:**
```bash
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
```

**結果:**
- **0件** - coreからanalysisへの依存は存在しない ✅

**証拠:**
- `docs/review_checklist.md` - 「core→analysis依存ゼロ」セクションを追加

---

### 5. 最終成果物（人間が判断できる形）

✅ **完了**

以下3点を「見れば一発でわかる」状態に：

1. **`docs/pipeline_graph.md`** - 依存図（core/analysis分離）
   - Mermaidグラフで可視化
   - CoreフローとAnalysisフローが明確に分離

2. **`docs/core_flow_table.md`** - 実行順序＋入出力＋証拠行
   - 各ステップの入出力を詳細に記録
   - 証拠行リンク（ファイル:行）を追加
   - 運用終点を明記

3. **`README.md`** - 運用コマンドと「終点ファイル」を明記
   - 運用フロー（core完結）を明記
   - 運用終点（`daily_portfolio_guarded.parquet`）を明記
   - Executionの入力として明記

---

## 成果物一覧

### ドキュメント

1. **`docs/pipeline_graph.md`** - パイプライン依存図（Mermaid）
2. **`docs/core_flow_table.md`** - coreフロー表（証拠行リンク付き）
3. **`docs/core_flow_summary.md`** - coreフロー要約
4. **`docs/review_checklist.md`** - 人間レビュー用チェックリスト（core→analysis依存ゼロ確認追加）
5. **`docs/final_verification.md`** - 最終検証結果（このファイル）

### README更新

- **`README.md`** - 運用フローと運用終点を明記

---

## 確認事項

### ✅ 依存図が1枚で読める

- `docs/pipeline_graph.md` のMermaid図で、日次運用の始点→終点が追える

### ✅ coreフロー表が実行順序と入出力を説明できる

- `docs/core_flow_table.md` で、各ステップの入出力と証拠行を記録

### ✅ daily_portfolio_guarded.parquetの生成コードと生成場所が確定している

- 生成元: `scripts/core/build_portfolio.py:63`
- 保存先: `data/processed/daily_portfolio_guarded.parquet`
- 実運用で使用可能な形式（weightカラムを含む）

### ✅ analysis側のスクリプトはcore生成物を読むだけ

- analysis側はcore生成物（parquet）を読み込む
- core生成物に書き戻さない（analysis側は読み取り専用）

### ✅ core→analysis依存ゼロ

- coreからanalysisへのimportが0件であることを確認

---

## 次のステップ

1. **回帰確認（推奨）**
   - `python scripts/core/build_portfolio.py` が正常に動作することを確認
   - `python scripts/core/run_equity01_eval.py` が正常に動作することを確認

2. **Execution実装時の参照**
   - `docs/core_flow_summary.md` を参照して運用終点を確認
   - `data/processed/daily_portfolio_guarded.parquet` の最新日を読み込む

