# AI駆動・日本株インテリジェント日次トレーディングシステム 研究開発計画書 Ver.1.6
### ― モメンタム×クイックFA＋Breadth PCA＋HMM＋EventGuard＋Intraweek＋Leverage ―  

---

## 1. 背景と目的
従来の裁量・高速依存型デイ戦略では汎用性・安定性・再現性に乏しい。  
現物・信用を併用しつつ、AIによるレジーム制御とイベント防御を備えた**日次完結型トレーディング基盤**を構築する。  

OOS（Out-of-Sample）で統計的有意なα（t>2）とSharpe≥0.9を確認し、  
将来的に完全自動（RPA）＋SLA管理下で稼働可能なフレームを実装する。

---

## 2. 成功指標（KPI）

| 区分 | 指標 | 目標値 |
|------|------|------|
| リターン | 年率リターン（原資基準） | ≥15〜20％ |
| リスク調整 | Sharpe | ≥0.9 |
| 安定性 | Calmar | ≥0.6 |
| テールリスク | 下位5%日損益 | ≥−0.5%以内 |
| 運用安定性 | 夜間SLA達成率 | 100%（連続10営業日） |
| レバ管理 | 1日VAR（原資基準） | ≤2% |
| EventGuard遅延 | 平均≤10分、最大≤30分 |
| Post-Loss反応 | 翌日適用率100% |

---

## 3. 戦略構成

### 3.1 銘柄スコアリング
- ユニバース：東証流動性上位20％  
- 特徴量：短中期モメンタム、出来高加速、過熱抑制、低ボラ、クイックFA（EPS改定・ROIC等）  
- 配分：

$$
w_i \propto \frac{(Score_i^+)^{\alpha}}{\sigma_i^{\beta}}
\alpha = 1.0,\quad \beta = 0.5
$$





- セグメント均等：Large/Mid/Small = 1/3ずつ  
- βドミナンス制約：|βᵢ|·wᵢ ≤ 0.05  
- Breadth均一化補正で過集中防止

---

### 3.2 β制御
- β目標：0.6 / 0.4 / 0.2（強気 / 中立 / 防御）  
- ETFで階段制御（単元単位）、現物で未満株補間  
- 実効β＝βlong − βETF·(QETF/NAV)  
- 逸脱|Δβ|>0.1で自動リチューン

---

### 3.3 レジーム判定（思考層）
- Breadth PCA＋Sticky-HMM＋BOCPD＋Rule-Logit  
- 学習180日／運用60日、最小滞在5日  
- 判定：R≥θH → 強気、R≤θL → 防御  
- −2σで新規停止、−3σで撤退

---

### 3.4 EventGuard（反射層）
- トリガー：先物5分≤−1%、USDJPY10分>1.5σ、VIX30分+10%、重要度≥4イベント  
- 作動：新規停止＋β=0.2、強制引成  
- 継続：最低5営業日、防御解除はBreadth改善4日で  
- Latency監視：発動遅延<30分を保証

---

### 3.5 GMI（Global Momentum Index）
```
GMI=0.5·Z(S&P先物)+0.3·Z(VIX^-1)+0.2·Z(USDJPY)
```
- GMI>0.5→強気寄り、<−0.5→防御寄り  
- Event週は無効化

---

### 3.6 Post-Loss Learning
- 損失日の原因コード：EVT / REG / βMis / MOM崩壊 / LQX  
- 翌日から安全側アクション（7日減衰適用）  
- 反実仮想（ノートレ／β0.2）で週次A/B評価  

---

### 3.7 Adaptive Loop
- SHAPドリフト>1.5σ×3日→Score再訓練（20日Ridge）  
- β逸脱>0.1×3日→βRetune  
- 高Zスコア銘柄のPnL<−1σ→ローテーション  
- 日次Quick／週次Full／月次Feature再選抜

---

### 3.8 Ensemble（NF×PR）
- **NF（Noise-Filtered）**：痛みは記録のみ、週次統計反映  
- **PR（Pain-Responsive）**：短期安全側反映（縮小のみ）  
- ゲーティング：
  - EventGuard=ON→wNF=0.9,wPR=0.1  
  - Breadth高→NF寄せ  
  - GMI強気→PR最大0.6  
- 乖離<0.2→β=0.2・PR上限0.3  
- 最終共分散最適化でβ/回転制約

---

### 3.9 Intraweek Overlay（週跨ぎ禁止）
- **週内（月〜金）完結、週末・祝前日は完全クローズ**  
- β：0.5/0.35/0.2  
- 金曜14:30新規停止、14:50強制フラット  
- Event/祝前：新規禁止＋β=0.2  

#### Overnight（平日内のみ）
| 区間 | 可否 | 代表シグナル |
|------|------|---------------|
| 月→木間 | 可 | 低ボラ・決算ドリフト・GMI追随 |
| 木→金 | 条件付可 | Event/祝前除外 |
| 金→月 | **禁止** | — |

#### Overnight適性管理
- 固定版：低ボラ・Quality・決算ドリフトなど事前登録  
- 動的版：同セクター×同レジーム×同GMI帯でVaR<1.5%なら可  
- 当面は固定採用、動的はShadow検証予定。

---

### 3.10 Multi-Horizon Ensemble（D × IW）
```
w = γ w(D) + (1−γ) w(IW)
```
- EventGuard=ON → γ=0.8  
- 週内Breadth悪化→γ=0.6  
- 木曜後半／祝前→IW縮小  
- corr(D,IW)<0.3→β=0.2、IW縮小  
- 共分散最適化でリスク最小＋回転上限τ=0.06  

---

### 3.11 Leverage Control（信用運用）
- 最大建玉倍率：2.0〜3.0×（現物＋信用）  
- 原資1日VAR ≤2%、βcap=0.9  
- Event週：自動1.0×上限  
- 維持率60%警戒で即縮小  
- 週次IW層はレバなし安全層  

| レジーム | β目標 | 想定レバ |
|-----------|--------|----------|
| 強気 | 0.6 | 2.5x |
| 中立 | 0.4 | 1.8x |
| 防御 | 0.2 | 1.2x |

---

## 4. データ／分析構成
```
/data/raw, /data/weekly_raw
/feature, /feature/weekly
/models, /exec, /ops, /research
```
MANUSとGitHubで統合管理。

---

## 5. 検証
SPA / MCS / Diebold–Mariano検定を使用。  
評価項目：Sharpe, Calmar, DD縮小率, 相関崩壊時挙動, β逸脱, 回転。

---

## 6. 運用／RPA実行
RPAで寄付成行・引成クローズ自動化。  
β逸脱・Event発動・Post-Loss適用を監査ログに保存。

---

## 7. 開発スケジュール
| Phase | 内容 | 期間 |
|-------|------|------|
| P0 | MANUS環境構築・Git連携 | 〜11/10 |
| P1 | Feature実装 | 〜11/17 |
| P2 | HMM＋EventGuard稼働 | 〜11/24 |
| P3 | Adaptive＋NF×PR統合 | 〜12/5 |
| P4 | Intraweek＋Multi-Horizon | 〜12/20 |
| P5 | PoCペーパートレード | 1月 |
| P6 | Fat-Trim（特徴削減・回転抑制） | 2月〜 |

---

## 8. 成果物
- Pythonソース（MANUS連携）  
- `orders_YYYYMMDD.csv`, `event_days.csv`  
- KPI / Leverage / Latencyレポート  
- PoC報告書・運用手順書  

---

## 9. 結論
> EventGuard × Regime × Post-Loss × Ensemble × Intraweek × Leverage  
> により「踏まない・負けにくい・早く立ち直る」AIトレーディング基盤を構築。  
> 2026年Q1にPoC完了、Q2に量産運用フェーズへ。

---

© 2025 Souta Nakatani / MANUS Project
