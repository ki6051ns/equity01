# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム

本リポジトリは **AI駆動・日本株インテリジェント日次トレーディングシステム（equity01）** の  
研究・開発・実装を行うプロジェクトです。

本 README は Ver2.1 の進捗に基づき更新されています。

---

## 🚀 プロジェクト概要

equity01 は以下を満たす「再現性・説明可能性・堅牢性のある日本株日次トレード」基盤を構築することを目的とします。

- モメンタム × クイックFA  
- Breadth PCA（市場広さ）  
- HMM（レジーム判定）  
- EventGuard（イベント防御）  
- Intraweek（週内ロジック）  
- β制御（ETFで近似）  
- Leverage 管理

最終的には **ALPHAERS（統合戦略）** のコンポーネントとして組み込まれます。

---

## 🧱 アーキテクチャ

```
equity01/
├─ data/
│   ├─ raw/              # 94銘柄のparquetデータ
│   ├─ processed/        # 特徴量・スコア・ポートフォリオ
│   └─ calendar/
├─ scripts/              # 各種データ処理・戦略実行
├─ features/             # feature builder modules
├─ models/               # モデル類（今後拡張）
├─ research/             # notebooks
└─ exec/                 # 実行系
```

---

## 🧪 現状の実装状況（2025/11 Ver2.1）

### 完成
- ✔ ユニバース（流動性上位20% → 94銘柄）
- ✔ parquet 価格データ基盤
- ✔ Feature Builder（ret / vol / ADV / Z-score）
- ✔ Scoring Engine v1.1
- ✔ EventGuard v0.2（決算フラグ＋soft guard）
- ✔ 単体ペーパートレード（スコア → PF → リターン）
- ✔ cutoff_policy（D-1 08:00 JST）

### 進行中
- ⏳ EventGuard v0.3（先物急変、VIX、為替）
- ⏳ Intraweek Overlay（週内ポジションの縮小/禁止）
- ⏳ β制御（ETF階段方式）
- ⏳ Multi-Horizon Ensemble

### 今後
- 🔜 ALPHAERS による統合ペーパートレード
- 🔜 ベータ運用（2026 Q2 目標）

---

## 📂 実行コマンド例

特徴量生成 → スコア生成 → PF構築 → ペーパートレード

```bash
python scripts/build_features.py
python scripts/build_portfolio.py
python scripts/paper_trade.py
```

---

## 📈 ペーパートレード結果（サマリ）

（例：94銘柄ユニバース）

- 年率: 13.5%
- Sharpe: 0.70
- 最大DD: -36%
- EventGuard オン状態で安定動作を確認

---

## 🛡 EventGuard（v0.2）

実装済：

- earnings_flag（決算イベント）
- guard_factor（soft guard）
- decision_date / trading_date 2軸ロジック

v0.3（開発中）：

- 先物5分変動チェック（-1%）
- USDJPY ±σ
- VIX +10%
- BOJ/FOMCスコア ≥4

---

## 🧠 技術スタック

- **ChatGPT**：要件定義・外部/内部設計
- **Cursor Pro**：コーディング・リファクタリング
- **Claude**：コード監査
- **GitHub**：バージョン管理

---

## 📜 ライセンス

（必要に応じて記載）

---

## 📮 連絡先

本プロジェクトは個人研究目的です。  
外部公開・issue対応・PR 受付は必要に応じて設定します。

