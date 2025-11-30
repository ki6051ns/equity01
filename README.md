# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 2.2 / Updated: 2025-11-30**

equity01 は **AI駆動 × 正統クオンツ** で構築する  
日本株の **インテリジェント日次トレーディングシステム** です。

本システムは ALPHAERS（統合戦略）のコア戦略として設計されており、  
**再現性・説明可能性・堅牢性**を重視しています。

---

# 🚀 プロジェクト概要

equity01 が目指すもの：

- **スコアドリブンの透明な構造（black-box 非依存）**
- **α/β の完全分離（relative α の明示化）**
- **イベント反射層（EventGuard）によるギャップ殺し**
- **週内ロジック（Intraweek）でのリスク制御**
- **β制御・ETF階段による市場中立性の強化**
- **Multi-Horizon / Parameter Ensemble による安定化**

最終的には ALPHAERS 全体の **エクイティ戦略レイヤー**として統合されます。

---

# 🧱 アーキテクチャ

equity01/
├─ data/
│ ├─ raw/ # 94銘柄のparquet（日次価格データ）
│ ├─ processed/ # feature / score / portfolio / guard
│ └─ calendar/ # 祝日・イベントカレンダー
│
├─ scripts/
│ ├─ build_features.py
│ ├─ scoring_engine.py
│ ├─ build_portfolio.py
│ ├─ event_guard.py
│ ├─ paper_trade.py
│ ├─ calc_alpha_beta.py # relative α算出
│ └─ ...
│
├─ features/ # feature builder modules
├─ models/ # model や regime 判定（将来）
├─ research/ # notebooks（検証・分析）
└─ exec/ # 実行系

yaml
コードをコピーする

---

# 🧪 実装状況（Ver2.2 / 2025-11）

## 🎯 **今回のハイライト（8th〜9th_commit）**
- **EventGuard v1.1 実装**  
  - FOMC / CPI / 雇用統計 / BOJ / メジャーSQ など  
    「must-kill イベント」の運用設計を確定  
  - **前日引けヘッジ → 当日引け解消** 方式を採用  
  - 決算除外は日付別で動作

- **α/β 分離フレーム完成（calc_alpha_beta v2）**  
  - ポートフォリオと TOPIX の CCリターンを比較  
  - 日次 / 累積の relative α を可視化  
  - ヘッジ部分も独立トラックで管理

- **paper_trade v2：PnL → Return に統一**  
  - 出力を Return 系に限定  
  - ALPHAERS のアンサンブル標準仕様に完全対応

- **ScoringEngineConfig を一本化**  
  - パラメータ変更が scoring_engine.py に集約  
  - build_portfolio の重複排除に成功

---

## ✔ 完成しているもの
- ユニバース（流動性上位20% → 94銘柄）
- parquet データ基盤
- Feature Builder（ret/vol/ADV/heat_flag）
- Scoring Engine v1.1（size bucket 正規化含む）
- EventGuard v1.1（決算 & マクロ警戒枠）
- daily_portfolio_guarded 出力整備
- ペーパートレード（Returnベース）
- calc_alpha_beta（relative α算出）
- cutoff_policy（D-1 08:00 JST）

---

## ⏳ 進行中（開発フェーズ）
- EventGuard v0.3（先物・為替・VIX 閾値）
- Intraweek Overlay（木→金 / 金→月 縮小）
- β制御（ETF階段で β ≈ 0.6/0.4/0.2）
- Multi-Horizon Ensemble（1日/3日/5日）

---

## 🔮 今後（2026Q1〜）
- ALPHAERS での multi-strategy ペーパートレード
- レジーム判定（Breadth PCA / HMM）
- パラメータアンサンブル（zscore × score）
- VAR 連動のレバレッジ管理

---

# 📂 実行コマンド

特徴量 → スコア → ポートフォリオ → ペーパートレード → αβ分析

```bash
python scripts/build_features.py
python scripts/build_portfolio.py
python scripts/paper_trade.py
python scripts/calc_alpha_beta.py
📈 パフォーマンス例（ペーパートレード）
年率: 13.5%

Sharpe: 0.70

最大DD: -36%

EventGuard v1.1 オンで安定稼働

（※ 現状は T→T+1 の単一ホライゾンでの初期指標）

🛡 EventGuard（v1.1）
実装済（今回の主成果）
決算除外（各日付ごとに除外）

マクロイベント（前日引けでヘッジ）

guard_factor（ヘッジ比率）

trading_date / decision_date の二軸管理

v0.3（開発中）
日経225先物（5分変動）

USDJPY（σ距離）

VIX上昇

BOJ/FOMC の LLMスコアリング（速報判定）

🔍 技術スタック
ChatGPT（設計・ドキュメント・仕様策定）

Cursor Pro（実装）

Claude（コード監査）

Pandas / NumPy / pyarrow

GitHub（CI/CD 兼 バージョン管理）

📮 連絡先
本プロジェクトは個人研究用途です。
issue や PR は内部開発フェーズに応じて随時対応します。
