# core_deprecated/ - 廃止されたcore実装

このディレクトリには、equity01/core/ から移動された廃止実装を配置しています。

## ファイル

- `scoring_engine_variants.py`: variant探索用の旧実装
  - 現在は `scripts/analysis/scoring_variants.py` に移行
  - `scripts/core/scoring_engine.py` が運用MVPとして採用されている

## 移動理由

- coreを1か所・1実装に統一するため
- variant探索機能を研究・実験用（analysis/）に分離するため
- 運用MVP（scripts/core/）を明確化するため

## 注意

これらのファイルは参照されていません。削除しても問題ありませんが、
履歴として残しています。

## 新しい使用先

- **運用MVP**: `scripts/core/scoring_engine.py`
- **variant探索**: `scripts/analysis/scoring_variants.py`

