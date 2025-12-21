# Core完結の生成パイプライン（運用MVP）

## 概要

core完結の生成パイプライン（始点→終点）を証拠行付きで可視化します。

**運用終点**: `data/processed/daily_portfolio_guarded.parquet`（Executionが読む正本）

---

## Core完結の生成図（Mermaid）

```mermaid
graph TD
    %% === 始点（生データ・設定） ===
    A1[data/raw/jpx_listings/*.csv] -->|universe_builder.py:229| B1[data/intermediate/universe/latest_universe.parquet]
    A2[data/raw/prices/*.csv] -->|build_index_tpx_daily.py:84| B2[data/processed/index_tpx_daily.parquet]
    A3[configs/universe.yml] -.->|universe_builder.py| B1
    A4[data/events/calendar.csv] -.->|build_portfolio.py EventGuard| F1
    A5[data/events/earnings.csv] -.->|build_portfolio.py EventGuard| F1
    
    %% === データ準備 ===
    B1 -->|download_prices.py:180| C1[data/raw/prices/prices_{ticker}.csv]
    
    %% === 特徴量構築 ===
    C1 -->|build_features.py:170| D1[data/processed/daily_feature_scores.parquet]
    B2 -.->|build_features.py:71| D1
    
    %% === ポートフォリオ構築（運用終点）===
    D1 -->|build_portfolio.py:63| F1[data/processed/daily_portfolio_guarded.parquet]
    
    %% スタイル
    classDef inputFile fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef coreEndpoint fill:#ffcdd2,stroke:#c62828,stroke-width:4px
    classDef coreOutput fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    classDef configFile fill:#fff3e0,stroke:#e65100,stroke-width:1px,stroke-dasharray: 3 3
    
    class A1,A2,A4,A5 inputFile
    class A3 configFile
    class F1 coreEndpoint
    class B1,B2,C1,D1 coreOutput
    
    %% ラベル追加
    F1:::coreEndpoint -.- END["★ 運用終点（Executionが読む正本）<br/>weight列必須<br/>最新日を読む"]
```

---

## 証拠行（コード位置）

### 1. universe_builder.py

- **入力読み込み**: [`scripts/core/universe_builder.py:61`](scripts/core/universe_builder.py#L61) (`pd.read_parquet(p_parq)`)
- **入力読み込み**: [`scripts/core/universe_builder.py:69`](scripts/core/universe_builder.py#L69) (`pd.read_parquet(p) if p.suffix==".parquet"`)
- **出力保存**: [`scripts/core/universe_builder.py:229`](scripts/core/universe_builder.py#L229) (`uni.to_parquet(out_path, index=False)`)

### 2. build_index_tpx_daily.py

- **出力保存**: [`scripts/tools/build_index_tpx_daily.py:84`](scripts/tools/build_index_tpx_daily.py#L84) (`df_output.to_parquet(out, index=False)`)

### 3. download_prices.py

- **入力読み込み**: [`scripts/core/download_prices.py:30`](scripts/core/download_prices.py#L30) (`pd.read_parquet(universe_path)`)
- **出力保存**: [`scripts/core/download_prices.py:180`](scripts/core/download_prices.py#L180) (`df.to_csv(out_path, index=False)`)

### 4. build_features.py

- **TOPIX入力読み込み**: [`scripts/core/build_features.py:71`](scripts/core/build_features.py#L71) (`df_tpx = pd.read_parquet(tpx_path)`)
- **TOPIX入力パス**: [`scripts/core/build_features.py:69`](scripts/core/build_features.py#L69) (`tpx_path = Path("data/processed/index_tpx_daily.parquet")`)
- **出力保存**: [`scripts/core/build_features.py:170`](scripts/core/build_features.py#L170) (`df_featured.to_parquet(out_path, index=False)`)
- **出力パス**: [`scripts/core/build_features.py:168`](scripts/core/build_features.py#L168) (`out_path = Path("data/processed/daily_feature_scores.parquet")`)

### 5. build_portfolio.py（運用終点生成）

- **入力読み込み**: [`scripts/core/build_portfolio.py:20`](scripts/core/build_portfolio.py#L20) (`df_features = pd.read_parquet(feat_path)`)
- **入力パス**: [`scripts/core/build_portfolio.py:19`](scripts/core/build_portfolio.py#L19) (`feat_path = Path("data/processed/daily_feature_scores.parquet")`)
- **出力保存**: [`scripts/core/build_portfolio.py:63`](scripts/core/build_portfolio.py#L63) (`df_port.to_parquet(out_path, index=False)`) ← **運用終点生成**
- **出力パス**: [`scripts/core/build_portfolio.py:61`](scripts/core/build_portfolio.py#L61) (`out_path = Path("data/processed/daily_portfolio_guarded.parquet")`)

---

## 運用終点の定義

**`data/processed/daily_portfolio_guarded.parquet`**

- **生成元**: `scripts/core/build_portfolio.py:63`
- **内容**: `weight` 列を含み、実運用で直接使用可能
- **使用方法**: Executionはこのファイルの最新日（latest date）の行を読み込む
- **必須カラム**: `date`, `symbol`, `weight`

---

## 実行順序

```bash
# 1. ユニバース構築
python scripts/core/universe_builder.py --config configs/universe.yml

# 2. 価格データ取得
python scripts/core/download_prices.py --universe data/intermediate/universe/latest_universe.parquet

# 3. TOPIXデータ構築
python scripts/tools/build_index_tpx_daily.py

# 4. 特徴量構築
python scripts/core/build_features.py

# 5. ポートフォリオ構築（運用終点生成）
python scripts/core/build_portfolio.py
# → 出力: data/processed/daily_portfolio_guarded.parquet（Executionが読む正本）
```

---

## 参照

- `docs/core_flow_table.md` - coreフロー表（詳細）
- `docs/pipeline_graph.md` - パイプライン依存図（統合版）

