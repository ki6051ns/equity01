# scripts/ 配下ファイル統合整理計画（最終版）

## 概要

equity01（JP-stg）の scripts/ および重複 core/ を全面的に精査し、
**prdで安全に動く最小運用セット（STOP + cross4）**と
**研究・探索・別PJ（parity）**を明確に分離する。

## 絶対ルール

1. **削除は禁止**（移動・隔離のみ）
2. **coreは1か所・1実装に統一**する
3. **同名ファイルの共存を禁止**
4. **variant探索で運用ロジックが変わらない構造**を作る

---

## 現状の問題点

### 1. 重複ファイルの存在

**core/scoring_engine.py** と **scripts/core/scoring_engine.py** が共存している。

- `core/scoring_engine.py`: variant探索用（SCORING_VARIANTS辞書とvariant計算ロジック）
- `scripts/core/scoring_engine.py`: 運用MVP用（ScoringEngineConfig, build_daily_portfolio）

現在、`scripts/core/` のファイルは `from core.scoring_engine import ...` としているが、
Pythonのimportは `core/scoring_engine.py` を優先して読み込むため、
実際には variant探索用の実装が使われている可能性がある。

### 2. ディレクトリ構造の不整合

- `equity01/core/` 配下：使用禁止とみなす必要がある
- `scripts/core/` 配下：prdで使う運用MVPとして統一する必要がある

---

## 統合方針

### フェーズ1: core/scoring_engine.py の整理

#### 1.1 variant探索機能の分離

`core/scoring_engine.py` の variant探索機能（`SCORING_VARIANTS`, `ScoringVariantConfig`, variant計算ロジック）を
`scripts/analysis/scoring_variants.py` に移動する。

**理由:**
- variant探索は研究・実験用途
- 運用MVPには含めない
- 探索用コードをanalysisに集約することで、coreを触らずに探索できる

#### 1.2 運用MVPの統一

`scripts/core/scoring_engine.py` を運用MVPとして採用。

**内容:**
- `ScoringEngineConfig`: 運用設定
- `build_daily_portfolio`: ポートフォリオ構築
- `compute_scores_all`: 基本スコア計算（z_lin, rank_only のみ）

#### 1.3 core/ のアーカイブ

`core/scoring_engine.py` を `archive/core_deprecated/scoring_engine.py` に移動し、DEPRECATEDコメントを付与。

---

## 統合手順

### ステップ1: variant探索機能の抽出

```bash
# 1. scoring_variants.py を作成（core/scoring_engine.pyからvariant部分を抽出）
mkdir -p scripts/analysis
# （手動で core/scoring_engine.py の variant部分を scripts/analysis/scoring_variants.py にコピー）
```

**抽出対象:**
- `ScoreType`, `ScoringVariantConfig`, `SCORING_VARIANTS`
- `compute_scores_all` 関数（variant計算ロジックを含む版）
- variant計算用のヘルパー関数

### ステップ2: scripts/core/scoring_engine.py の確認・補完

`scripts/core/scoring_engine.py` が以下を含むことを確認：

- `ScoringEngineConfig`
- `build_daily_portfolio`
- `compute_scores_all`（基本版：z_lin, rank_only のみ）
- `run_from_config`
- `_zscore` ヘルパー関数（build_features.pyから使用される）

**不足している場合は補完する。**

### ステップ3: core/ のアーカイブ

```bash
# archive ディレクトリを作成
mkdir -p archive/core_deprecated

# core/scoring_engine.py を移動
mv core/scoring_engine.py archive/core_deprecated/scoring_engine_variants.py

# DEPRECATEDコメントを追加
cat > archive/core_deprecated/README.md << 'EOF'
# core_deprecated/ - 廃止されたcore実装

このディレクトリには、equity01/core/ から移動された廃止実装を配置しています。

## ファイル

- `scoring_engine_variants.py`: variant探索用の旧実装
  - 現在は `scripts/analysis/scoring_variants.py` に移行
  - `scripts/core/scoring_engine.py` が運用MVPとして採用されている

## 注意

これらのファイルは参照されていません。削除しても問題ありませんが、
履歴として残しています。
EOF
```

### ステップ4: importパスの修正

`scripts/core/` 配下のファイルで `from core.scoring_engine import ...` を
`from scripts.core.scoring_engine import ...` または相対importに修正。

**修正対象ファイル:**
- `scripts/core/build_features.py`
- `scripts/core/build_portfolio.py`
- `scripts/core/run_scoring.py`

**修正例:**
```python
# 修正前
from core.scoring_engine import ScoringEngineConfig, build_daily_portfolio

# 修正後（相対import推奨）
from .scoring_engine import ScoringEngineConfig, build_daily_portfolio

# または（絶対importの場合）
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from scripts.core.scoring_engine import ScoringEngineConfig, build_daily_portfolio
```

### ステップ5: core/__init__.py の処理

`core/__init__.py` が存在する場合、これもアーカイブ対象。

```bash
# core/ ディレクトリが空になる場合
mv core/__init__.py archive/core_deprecated/__init__.py
# または core/ ディレクトリごとアーカイブ
```

---

## 統合後のディレクトリ構造

```
equity01/
├── archive/
│   └── core_deprecated/
│       ├── README.md
│       ├── scoring_engine_variants.py
│       └── __init__.py (if exists)
├── scripts/
│   ├── core/                    # 運用MVP（prdで使用）
│   │   ├── scoring_engine.py   # 統一された運用実装
│   │   ├── build_portfolio.py
│   │   ├── build_features.py
│   │   └── ...
│   └── analysis/
│       ├── scoring_variants.py  # variant探索用（新規）
│       └── ...
└── core/                        # 空になるか削除対象
```

---

## 回帰確認

### 確認項目

1. **importエラーの確認**
   ```bash
   python -m py_compile scripts/core/*.py
   python -c "import sys; sys.path.insert(0, 'scripts'); from scripts.core.scoring_engine import ScoringEngineConfig; print('OK')"
   ```

2. **実行フローの確認**
   ```bash
   # 1. 特徴量構築
   python scripts/core/build_features.py
   
   # 2. スコアリング
   python scripts/core/run_scoring.py
   
   # 3. ポートフォリオ構築
   python scripts/core/build_portfolio.py
   
   # 4. 評価パイプライン
   python scripts/core/run_equity01_eval.py
   ```

3. **STOP + cross4 の確認**
   ```bash
   # 統合評価レポート
   python scripts/analysis/run_eval_report.py
   
   # STOP検証
   python scripts/analysis/eval_stop_regimes.py
   python scripts/analysis/eval_stop_regimes_robustness.py
   ```

---

## 注意事項

### 1. variant探索コードの分離

variant探索用のコード（`SCORING_VARIANTS` など）を `scripts/analysis/scoring_variants.py` に分離することで、
**coreを触らずに探索できる構造**を実現する。

運用側（`scripts/core/scoring_engine.py`）では variant計算ロジックを保持せず、
設定ファイル（`configs/scoring.yml`）でvariantを切り替える方式にする。

### 2. 後方互換性

`compute_scores_all` 関数は `scripts/core/scoring_engine.py` に残すが、
variant計算ロジックは含めず、基本版（z_lin, rank_only）のみ提供する。

variant探索が必要な場合は `scripts/analysis/scoring_variants.py` を使用する。

### 3. importパスの統一

全ての `scripts/core/` 配下のファイルで、
`from core.xxx` ではなく相対import（`from .xxx`）または
明確な絶対import（`from scripts.core.xxx`）を使用する。

---

## 成果物

1. **docs/file_inventory.csv**（更新）
   - core/scoring_engine.py → archive/core_deprecated/scoring_engine_variants.py
   - scripts/analysis/scoring_variants.py（新規）を追加

2. **docs/cleanup_plan.md**（更新）
   - 統合手順を反映

3. **archive/core_deprecated/README.md**（新規）
   - アーカイブ理由の説明

