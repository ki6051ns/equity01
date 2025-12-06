# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 2.3 / Updated: 2025-12-04**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

本システムは ALPHAERS（統合戦略）の中心に位置する **エクイティ戦略レイヤー**であり、  
**透明性、説明可能性、再現性（replicability）、堅牢性（robustness）** を最優先事項とします。

---

# 🚀 プロジェクト概要

equity01 が目指す到達点：

- **black-box に依存しない透明なスコア駆動構造**  
- **α/β の完全分離（relative α の可視化）**
- **EventGuard によるイベントリスク遮断（ギャップ殺し）**
- **週内ロジック（Intraweek Overlay）によるリスク抑制**
- **β制御（ETF階段）による市場中立性の改善**
- **Multi-Horizon / Parameter Ensemble による α の安定化と強化**

最終的には、ALPHAERS 全体の内部で

> **エクイティ・モジュール（Equity Alpha Engine）として常時稼働**

することを目的とします。

---

# 🧱 アーキテクチャ構造（2025-12 Ver）

equity01/
├─ data/
│ ├─ raw/ # 日次価格パネル（94銘柄）
│ ├─ processed/ # feature, score, portfolio, guard, ensemble 結果
│ └─ calendar/ # 祝日・macro event カレンダー
│
├─ scripts/
│ ├─ build_features.py
│ ├─ scoring_engine.py
│ ├─ build_portfolio.py
│ ├─ event_guard.py
│ ├─ paper_trade.py
│ ├─ run_single_horizon.py # H1〜H120 ラダーBT
│ ├─ compare_ladder_vs_baseline.py
│ ├─ calc_alpha_beta.py # relative α算出
│ └─ ...
│
├─ features/ # feature builder modules
├─ models/ # regime 判定（PCA/HMM）（将来）
├─ research/ # notebooks / 分析
└─ exec/ # 実行・デプロイ用

yaml
コードをコピーする

---

# 🧪 実装状況（Ver 2.3 / 2025-12）

## 🎯 **今回のハイライト（8th → 9th → 10th commit）**

---

# ✅ **10th_commit（最新）**  
## 🟦 **ラダー方式（non-overlap horizon）の採用と全ホライゾン解析**

### 🔥 問題：overlapping horizon の構造的欠陥  
従来の H1/H3/H5/H10… は

- 同じ日付に同銘柄のシグナルが複数重複  
- αが過大評価される  
- ノイズが増幅  
- 実運用再現性が低い

という、クオンツ戦略では致命的なバイアスを生んでいた。

---

## 🔥 解決：**完全ラダー方式（non-overlap horizon）を導入**

### 実装済ホライゾン
- **H1 / H5 / H10 / H20 / H60 / H90 / H120**

### 結果：全ホライゾンで **非ラダー vs ラダー** の比較  
特に **H60 / H90 / H120** が圧倒的に優秀。

---

## 🔥 パフォーマンス総括（抜粋）

### **H90（最強）**
- Port累積：**+269%**（非ラダー +215% を圧倒）
- Sharpe：**0.733**
- relative α：**+130%**

### **H120**
- Port累積：+262%
- Sharpe：0.718  
- relative α：+123%

### **H60**
- Port累積：+259%
- Sharpe：0.718  
- relative α：+120%

---

## 🔧 **結論：アンサンブル採用ホライゾン**
| グループ | ホライゾン | 役割 |
|---------|-------------|-------|
| **コア採用** | **H60 / H90 / H120（ラダー）** | α源泉の主力。Sharpe>0.70 |
| **サブ採用** | H5 / H10（非ラダー） | 週内効果を補完するため少量採用 |
| **抑制** | H1 / H20 | ノイズ多いためウェイト縮小 |

これにより **安定性＋再現性＋汎用性** が大幅改善。

---

# ✅ **9th_commit（α/β 分離・Return標準化）**

### ✔ paper_trade 出力を Return に統一  
- daily_return  
- daily_return_alpha  
- daily_return_hedge  
- equity  
- drawdown  

ALPHAERS の他ストラテジーとの **アンサンブル互換性**が確立。

---

### ✔ calc_alpha_beta v2  
- Port CC return  
- TOPIX CC return  
- relative α  
- β要素を完全切り離し可能に。

---

# ✅ **8th_commit（EventGuard v1.1）**

### ✔ must-kill イベントの体系化  
- FOMC  
- CPI  
- 雇用統計  
- BOJ（決定会合＋会見）  
- メジャーSQ  

**前日引けヘッジ → 当日引け解消** が標準動作。

### ✔ 決算除外ロジック（date-based）  
event01（カレンダー）から自動フィードされる設計。

---

# ✔ 完成済（2025-12）

- 94銘柄ユニバース（流動性上位20%）
- parquetデータ基盤
- Feature Builder（ret/vol/ADV/heat_flag）
- Scoring Engine v1.1（サイズバケット正規化）
- EventGuard v1.1
- daily_portfolio_guarded 出力完成
- PaperTrade v2（Return に統一）
- Ladder Backtest（H1〜H120）
- calc_alpha_beta（relative α）

---

# ⏳ 開発中（2026Q1 完成予定）

## 🔵 EventGuard v0.3  
- 225先物（5分変動）  
- USDJPY（σ距離）  
- VIX  
- ニュース速報 event02  
- VAR連動リスク調整

## 🔵 Intraweek Overlay  
- 木→金、金→月の縮小ロジック  
- 月曜リスクの軽減

## 🔵 β制御  
- ETF階段（β 0.6 / 0.4 / 0.2）  
- ボラターゲティング

---

# 🔮 今後のロードマップ（2026）

## 🟣 Multi-Horizon Ensemble（次フェーズ）
final_w = a·H60 + b·H90 + c·H120 + ε(H5,H10)

shell
コードをコピーする

## 🟣 パラメータアンサンブル
w_final = (1-λ)·w_zscore + λ·w_score

yaml
コードをコピーする

## 🟣 Regime 判定（2026Q2）
- Breadth PCA  
- HMM / Sticky-HMM  
- Regime-based weight multipliers  

---

# 📂 実行コマンド（標準フロー）

python scripts/build_features.py
python scripts/build_portfolio.py
python scripts/run_single_horizon.py 60 # 例
python scripts/paper_trade.py
python scripts/calc_alpha_beta.py

yaml
コードをコピーする

---

# 📈 スナップショット（H90 ラダー）

- 年率: **14.56%**  
- Sharpe: **0.733**  
- 最大DD: -35.2%  
- α累積: **+130%**

> EventGuard v1.1 稼働時  
> 実運用想定に耐える戦略クオリティに到達。

---

# 🛡 EventGuard（v1.1 → v0.3）

### 現行（v1.1）
- 決算除外  
- macroイベントヘッジ  
- hedge_ratio  
- decision/trading date

### v0.3（開発中）
- ニュースイベント（event02）  
- 225先物 × USDJPY  
- LLM 要約判定  
- σ距離ベースの risk-off detection

---

# 🔍 技術スタック
- ChatGPT（設計・仕様・研究）
- Cursor Pro（実装）
- Claude（コード監査）
- Pandas / PyArrow
- GitHub（versioning）

---

# 📮 連絡先
本プロジェクトは個人研究目的で進行しています。  
issue / PR は内部フェーズに応じて対応予定。
