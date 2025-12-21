# core統合記録（equity01/core/ と scripts/core/ の重複解消）

## 概要

equity01/core/ と scripts/core/ の同名ファイルの重複問題を解消し、scripts/core/ を唯一の正として統一しました。

---

## 実施日

2025-01-XX

---

## 重複ファイル一覧と解消状況

### scoring_engine.py

**equity01/core/scoring_engine.py:**
- **内容**: variant探索用の実装（SCORING_VARIANTS辞書とvariant計算ロジック）
- **用途**: 研究・実験用
- **状態**: `archive/core_deprecated/scoring_engine_variants.py` に移動（DEPRECATED）

**scripts/core/scoring_engine.py:**
- **内容**: 運用MVP用の実装（ScoringEngineConfig, build_daily_portfolio, compute_scores_all基本版）
- **用途**: 運用固定
- **状態**: **採用**（唯一の正）

**統合方針:**
1. variant探索機能を `scripts/analysis/scoring_variants.py` に分離
2. `scripts/core/scoring_engine.py` を運用MVPとして統一
3. `core/scoring_engine.py` を `archive/core_deprecated/` に移動

**importパス修正:**
- `scripts/core/build_features.py`: `from scripts.core.scoring_engine import compute_scores_all, _zscore`
- `scripts/core/build_portfolio.py`: `from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio`
- `scripts/core/run_scoring.py`: `from scripts.core.scoring_engine import run_from_config`

---

## 他の重複ファイル

### __init__.py

**equity01/core/__init__.py:**
- **内容**: `# core package`
- **状態**: `archive/core_deprecated/__init__.py` に移動

**scripts/core/__init__.py:**
- **存在**: なし（不要）

---

## 統合後のディレクトリ構造

```
equity01/
├── archive/
│   └── core_deprecated/
│       ├── README.md
│       ├── scoring_engine_variants.py  # 旧実装（DEPRECATED）
│       └── __init__.py
├── scripts/
│   └── core/
│       ├── scoring_engine.py  # 統一された運用実装（唯一の正）
│       └── ...
└── core/  # 空または削除対象
```

---

## 統合方針の原則

1. **scripts/core/ を唯一の正とする**
   - 運用MVPとして統一
   - 全てのimportパスは `from scripts.core.xxx import ...` を使用

2. **equity01/core/ は使用禁止**
   - 全てのファイルを `archive/core_deprecated/` に移動
   - または削除（参照がない場合）

3. **variant探索機能の分離**
   - variant探索用のコードは `scripts/analysis/` に配置
   - coreを触らずに探索が可能な構造を維持

---

## 実施内容

### 1. variant探索機能の分離

- `core/scoring_engine.py` の variant探索機能を `scripts/analysis/scoring_variants.py` に抽出
- `SCORING_VARIANTS` 辞書と `compute_scores_all_variants` 関数を分離

### 2. 運用MVPの統一

- `scripts/core/scoring_engine.py` を運用MVPとして統一
- `ScoringEngineConfig`, `build_daily_portfolio`, `compute_scores_all`（基本版）を含む

### 3. アーカイブ

- `core/scoring_engine.py` を `archive/core_deprecated/scoring_engine_variants.py` に移動
- `core/__init__.py` を `archive/core_deprecated/__init__.py` に移動
- DEPRECATEDコメントを付与

### 4. importパス修正

- `scripts/core/` 配下のファイルで `from core.xxx import ...` を `from scripts.core.xxx import ...` に統一

---

## 確認事項

### 構文チェック

```bash
python -m py_compile scripts/core/*.py
```

結果: ✅ エラーなし

### import確認

```bash
python -c "import sys; sys.path.insert(0, 'scripts'); from scripts.core.scoring_engine import ScoringEngineConfig; print('OK')"
```

結果: ✅ 正常に動作

---

## 参照ファイル

- `docs/unified_cleanup_summary.md` - 統合整理の実施サマリ
- `archive/core_deprecated/README.md` - アーカイブ理由の説明
- `scripts/analysis/scoring_variants.py` - variant探索用の新実装

