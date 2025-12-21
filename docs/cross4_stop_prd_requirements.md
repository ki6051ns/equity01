# cross4/STOPのprd最小要件分離

## 概要

cross4/STOPのprdで必要な最小要件を分離し、core終点（daily_portfolio_guarded）を消さない設計にします。

---

## STOPのprd最小要件

### 現状

STOPは「執行停止フラグ」を返すだけにし、core終点（daily_portfolio_guarded）を消さない設計にする。

**設計方針:**
- STOPは執行停止フラグ（boolean）を返すだけ
- core終点（`daily_portfolio_guarded.parquet`）は削除しない
- Executionは `daily_portfolio_guarded.parquet` を読み、STOPフラグを確認して執行可否を判断

**実装案:**
```python
# scripts/core/check_stop_flag.py（新規作成案）
def check_stop_flag(date: str) -> bool:
    """
    STOPフラグを確認する
    
    Parameters
    ----------
    date : str
        確認する日付（YYYY-MM-DD）
    
    Returns
    -------
    bool
        True: 執行停止, False: 執行可能
    """
    # regime_labels.parquet からレジームを読み込み
    # レジームが「弱レジーム」の場合は True を返す
    ...
```

**注意:**
- STOPフラグは `data/processed/regime_labels.parquet` から読み込む（analysis側で生成）
- core終点（`daily_portfolio_guarded.parquet`）は削除しない
- Executionは両方を読み込んで判断

---

## cross4のprd最小要件

### 現状

cross4は現状「研究上の合成パフォーマンス」なので、prdで"cross4ターゲットウェイト"を本当に使うなら、別途 `target_weights_cross4_latest.parquet` を設計してcoreに実装する（未実装のまま放置しない）。

**設計方針:**
- 現状: cross4は研究用（`horizon_ensemble_variant_cross4.parquet`）
- prdで使用する場合: `target_weights_cross4_latest.parquet` を新規設計

**実装案（prdで使用する場合）:**
```python
# scripts/core/build_target_weights_cross4.py（新規作成案）
def main():
    """
    cross4からターゲットウェイトを生成する
    
    入力:
    - horizon_ensemble_variant_cross4.parquet（analysis側で生成）
    
    出力:
    - target_weights_cross4_latest.parquet（core側で生成）
    """
    # cross4アンサンブルを読み込み
    df_cross4 = pd.read_parquet("data/processed/horizon_ensemble_variant_cross4.parquet")
    
    # ターゲットウェイトを計算
    # ... 実装 ...
    
    # 保存
    df_weights.to_parquet("data/processed/target_weights_cross4_latest.parquet", index=False)
```

**注意:**
- 現状は未実装（研究用のまま）
- prdで使用する場合は、上記の実装案を参考にcore側に実装する
- **未実装のまま放置しない**

---

## core終点の保護

### 運用終点の固定

**`data/processed/daily_portfolio_guarded.parquet`** がcoreフローの運用終点です。

**保護方針:**
- core終点は削除しない
- STOPフラグは別途確認する
- cross4ターゲットウェイトは別途設計する（未実装のまま放置しない）

---

## 参照

- `docs/core_pipeline_complete.md` - core完結の生成パイプライン
- `docs/cross4_stop_analysis_fixed.md` - cross4/STOPの扱い
- `docs/analysis_research_pipeline.md` - analysis研究フロー

