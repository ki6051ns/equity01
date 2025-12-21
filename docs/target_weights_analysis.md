# target_weights_latest.parquet 生成について

## 現状分析

### 現在の終点

**`data/processed/daily_portfolio_guarded.parquet`** が coreフローの実質的な終点です。

**内容:**
- `date` / `trading_date` / `decision_date` - 日付情報
- `symbol` - 銘柄コード
- `size_bucket` - サイズバケット（Large/Mid/Small）
- `feature_score` - 特徴量スコア
- `z_score_bucket` - バケット内Z-score
- `selected` - 選定フラグ
- `weight` - **ウェイト（実運用で使用可能）**
- `hedge_ratio` - ヘッジ比率
- `inverse_symbol` - インバースETFシンボル

**結論:**
- `daily_portfolio_guarded.parquet` には既に `weight` カラムが含まれています
- 実運用で直接使用可能な形式です

---

## target_weights_latest.parquet の必要性

### オプションA: daily_portfolio_guarded.parquet をそのまま使用（推奨）

**メリット:**
- 追加のスクリプト不要
- 既存のフローを変更する必要がない
- メタデータ（size_bucket, z_score_bucket等）も含まれており、デバッグに便利

**デメリット:**
- ファイル名が「guarded」で、終点としての意図が明確でない

**推奨:**
- **このオプションを採用**し、`daily_portfolio_guarded.parquet` を実質的な終点として使用

---

### オプションB: target_weights_latest.parquet を生成

**実装案:**
```python
# scripts/core/build_target_weights.py
"""
daily_portfolio_guarded.parquet から target_weights_latest.parquet を生成

実運用で使用するためのクリーニング済みウェイトを生成します。
"""
from pathlib import Path
import pandas as pd
from scripts.tools.weights_cleaning import clean_target_weights

def main():
    # daily_portfolio_guarded.parquet を読み込み
    df_port = pd.read_parquet("data/processed/daily_portfolio_guarded.parquet")
    
    # 最新日のポートフォリオを取得
    latest_date = df_port["date"].max()
    df_latest = df_port[df_port["date"] == latest_date].copy()
    
    # ウェイトをクリーニング（weights_cleaning.pyを使用）
    # ... 実装 ...
    
    # target_weights_latest.parquet として保存
    out_path = Path("data/processed/target_weights_latest.parquet")
    df_target.to_parquet(out_path, index=False)
```

**メリット:**
- ファイル名が明確（終点であることがわかりやすい）
- 実運用での使用意図が明確

**デメリット:**
- 追加のスクリプトが必要
- メタデータが失われる可能性

**推奨:**
- 現時点では不要（daily_portfolio_guarded.parquet で十分）

---

## 推奨対応

### 結論

**`daily_portfolio_guarded.parquet` を実質的な終点として使用します。**

**理由:**
1. 既に `weight` カラムが含まれている
2. EventGuardが適用済みで実運用で使用可能
3. メタデータも含まれており、デバッグに便利
4. 追加のスクリプト不要

### ドキュメントでの明記

以下のドキュメントで `daily_portfolio_guarded.parquet` を終点として明記：

- `docs/core_flow_table.md` - 終点として明記済み
- `docs/pipeline_graph.md` - 終点として明記済み
- `README.md` - 必要に応じて更新

---

## 将来の拡張（必要に応じて）

将来的に `target_weights_latest.parquet` が必要になった場合：

1. `scripts/core/build_target_weights.py` を新規作成
2. `daily_portfolio_guarded.parquet` を読み込み
3. `weights_cleaning.py` を使用してクリーニング
4. `target_weights_latest.parquet` として保存
5. `run_equity01_eval.py` にステップとして追加

ただし、現時点では不要と判断します。

