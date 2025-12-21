# 最終確認チェックリスト

## 実施日

2025-01-XX

---

## ✅ 確認項目

### 1. 運用MVP（core）の始点→終点が1枚のMermaid図に確定

- [x] `docs/pipeline_graph.md` のCoreフロー図を更新
- [x] 運用終点（`daily_portfolio_guarded.parquet`）を明確化
- [x] 評価パイプライン（`run_equity01_eval.py`）を評価用として明記
- [x] 証拠行（行番号）を図に追加

**確認:**
- `docs/pipeline_graph.md` - 「Coreフロー（運用MVP）始点→終点」セクション

---

### 2. 証拠行（行番号）をリンク可能な形で揃える

- [x] 各スクリプトの入出力（read_parquet/to_parquet/to_csv）の行番号を抽出
- [x] `docs/core_flow_table.md` に「証拠行（コード位置）」として追記
- [x] GitHubで見やすいように `path:line` 形式を統一（例：`scripts/core/build_portfolio.py:61-63`）
- [x] リンク形式（`[text](path#Lline)`）を使用

**確認:**
- `docs/core_flow_table.md` - 各ステップの「証拠行（コード位置）」セクション

---

### 3. cross4/STOPの扱いをanalysis固定にし、coreへ混線させない

- [x] cross4/STOP系をanalysis側の系統として明確化
- [x] coreフロー（運用終点）とcross4/STOPが混線していないことを確認
- [x] `build_regime_hmm.py` の位置づけを明確化（KEEP_STG_ANALYSIS）
- [x] core→analysis依存ゼロを確認（0件）

**確認:**
- `docs/cross4_stop_analysis_fixed.md` - cross4/STOPの扱い
- `docs/core_flow_table.md` - 「cross4 と STOP の扱い（analysis固定）」セクション

---

### 4. variant探索はanalysis側で完結、core/run_scoring.pyは触るな

- [x] variant探索は `scripts/analysis/scoring_variants.py` で完結
- [x] `scripts/core/run_scoring.py` と `scripts/core/scoring_engine.py` は運用固定（変更禁止）を明記
- [x] 変更が必要な場合の手順（危険度の明示、代替案の提案）を文書化

**確認:**
- `docs/variant_exploration_rules.md` - variant探索ルール
- `docs/core_unification.md` - core統合記録

---

### 5. 終点ファイルの中身を確認できるチェックスクリプトを提案

- [x] `scripts/tools/check_target_weights.py` を作成
- [x] 確認項目を実装：
  - symbol / weight / date が揃っている
  - weight が合計1（または仕様通り）
  - 0やNaNや重複がない
  - 最新日が存在する

**確認:**
- `scripts/tools/check_target_weights.py` - チェックスクリプト

---

## 📋 成果物一覧

### ドキュメント

1. **`docs/pipeline_graph.md`** - パイプライン依存図（Mermaid、証拠行付き）
2. **`docs/core_flow_table.md`** - coreフロー表（証拠行リンク付き）
3. **`docs/cross4_stop_analysis_fixed.md`** - cross4/STOPの扱い（analysis固定）
4. **`docs/variant_exploration_rules.md`** - variant探索ルール（core固定原則）
5. **`docs/final_checklist.md`** - 最終確認チェックリスト（このファイル）

### スクリプト

1. **`scripts/tools/check_target_weights.py`** - 運用終点ファイルの内容確認スクリプト

---

## 🔍 確認コマンド

### core→analysis依存ゼロの確認

```bash
rg -n "scripts\.analysis|from scripts\.analysis|import scripts\.analysis" scripts/core
# 結果: 0件 ✅
```

### 運用終点ファイルの確認

```bash
python scripts/tools/check_target_weights.py
python scripts/tools/check_target_weights.py --verbose
```

---

## ✅ 全ての確認項目をクリア

全ての確認項目が完了しています。

