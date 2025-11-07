# AI駆動・日本株インテリジェント日次トレーディングシステム 研究開発計画書 **Ver.1.61**
### ― モメンタム×クイックFA＋Breadth PCA＋HMM＋EventGuard＋Intraweek＋Leverage ―  

> **更新点（v1.61）**：主要式をすべて数式（GitHub数式レンダリング）で明記。重み付け、β実効、GMI、目的関数、制約、アンサンブル、適応学習など。

---

## 1. 背景と目的
従来の裁量・高速依存型デイ戦略では汎用性・安定性・再現性に乏しい。  
現物・信用を併用しつつ、AIによるレジーム制御とイベント防御を備えた**日次完結型トレーディング基盤**を構築する。  

OOS（Out-of-Sample）で統計的有意なα（$t>2$）と Sharpe $\ge 0.9$ を確認し、  
将来的に完全自動（RPA）＋SLA管理下で稼働可能なフレームを実装する。

---

## 2. 成功指標（KPI）

| 区分 | 指標 | 目標値 |
|------|------|------|
| リターン | 年率リターン（原資基準） | $\ge 15\% \sim 20\%$ |
| リスク調整 | Sharpe | $\ge 0.9$ |
| 安定性 | Calmar | $\ge 0.6$ |
| テールリスク | 下位5%日損益 | $\ge -0.5\%$ |
| 運用安定性 | 夜間SLA達成率 | 100%（連続10営業日） |
| レバ管理 | 1日VAR（原資基準） | $\le 2\%$ |
| EventGuard遅延 | 平均$\le 10$分、最大$\le 30$分 |
| Post-Loss反応 | 翌日適用率 100% |

---

## 3. 戦略構成

### 3.1 銘柄スコアリング

#### 3.1.1 特徴量スコアの合成
特徴量ベクトルを $x_i \in \mathbb{R}^K$、その標準化を $z_i$、重みを $w \in \mathbb{R}^K$ とすると、銘柄 $i$ の総合スコアは  
$$
S_i \;=\; w^\top z_i \;+\; \lambda_{\text{rev}}\; Z(\text{EPS\_Revision}_i)\;-\;\lambda_{\text{over}}\; \text{Overheat}_i\;-\;\lambda_{\text{liq}}\; \text{Illiq}_i.
$$

- $Z(\cdot)$ は分位または$z$スコア化。  
- $\text{Overheat}_i$：VWAP乖離・連騰・ギャップ等の過熱ペナルティ。  
- $\text{Illiq}_i$：スプレッド・ADV比等の流動性ペナルティ。

#### 3.1.2 配分（部分逆ボラ化＋分位）
分位スコア $\tilde S_i \in [0,1]$ を用い、部分逆ボラ係数 $\beta \in [0,1]$ で重み候補を
$$
\hat{w}_i \;\propto\; \frac{(\max\{\tilde S_i,0\})^{\alpha}}{\sigma_{20,i}^{\,\beta}}
\quad\text{（初期： }\alpha=1.0,\ \beta=0.5\text{）.}
$$

セグメント（Large/Mid/Small）均等化：
$$
\sum_{i \in \mathcal{G}_g} w_i \;=\; \frac{1}{3},\qquad g \in \{\text{L, M, S}\}.
$$

βドミナンス制約：
$$
| \beta_i |\, w_i \;\le\; c_{\beta}\quad(\text{初期 } c_{\beta}=0.05).
$$

#### 3.1.3 最終仕上げ（L1近接＋容量）
候補重み $\hat w$ から最終重み $w$ へ：
$$
\min_{w}\ \ (w-\hat w)^\top \Sigma (w-\hat w)
\quad \text{s.t.}\quad
\|w-\hat w\|_1 \le \tau,\quad
\sum_i |w_i-w_i^{\text{prev}}| \le \kappa,\quad
0 \le w_i \le u_i.
$$

---

### 3.2 β制御（現物×ETF）
目標 $\beta^\*\in\{0.6,0.4,0.2\}$（強気/中立/防御）。実効βは
$$
\beta_{\text{eff}} \;=\; \beta_{\text{long}} \;-\; \beta_{\text{ETF}}\cdot \frac{Q_{\text{ETF}}}{\text{NAV}}.
$$

逸脱が
$$
|\beta_{\text{eff}} - \beta^\*| > \Delta_\beta \quad(\Delta_\beta=0.1)
$$
なら再調整（ETF単元階段＋現物未満株で補間）。

---

### 3.3 レジーム判定（思考層）
Breadthから主成分 $p_t$ を抽出して $z$化。Sticky-HMMにより状態 $r_t \in \{\text{BULL},\text{NEUTRAL},\text{DEF}\}$ を推定：
$$
r_t \;=\; \arg\max_{s\in\mathcal{S}} \Pr(s_t=s \mid p_{1:t}).
$$
ヒステリシス閾値：
$$
\text{BULL} \;\text{ if }\; R_t \ge \theta_H,\quad
\text{DEF} \;\text{ if }\; R_t \le \theta_L,\quad
\text{else NEUTRAL}.
$$
ハードストップ：$p_t \le -2\sigma \Rightarrow$ 新規停止、$p_t \le -3\sigma \Rightarrow$ 撤退。

---

### 3.4 EventGuard（反射層）
即時防御フラグ
$$
\text{EG}_t \;=\; \mathbb{1}\!\left[
\Delta f^{(5m)}_{\text{fut}} \le -1\%
\;\lor\;
\frac{\Delta \text{USDJPY}^{(10m)}}{\sigma_{10m}} \ge 1.5
\;\lor\;
\frac{\Delta \text{VIX}^{(30m)}}{\text{VIX}_{t-30m}} \ge 10\%
\;\lor\;
\text{Imp}(t) \ge 4
\right].
$$
作動時：新規停止、$\beta^\*\!=0.2$、強制クローズ。解除は翌営業日9:00以降。

---

### 3.5 GMI（Global Momentum Index）
朝8:00時点で
$$
\text{GMI}_t \;=\; 0.5\cdot Z(\Delta \text{S\&P fut}) \;+\; 0.3\cdot Z(\text{VIX}^{-1}) \;+\; 0.2\cdot Z(\Delta \text{USDJPY}).
$$
判定：
$$
\text{GMI}_t > 0.5 \Rightarrow \text{強気寄り},\qquad
\text{GMI}_t < -0.5 \Rightarrow \text{防御寄り}.
$$
（イベント前後$\pm 1$日は無効化）

---

### 3.6 Post-Loss Learning（翌日反映）
日次PnLの回帰分解：
$$
r_t \;=\; \alpha_t \;+\; \beta_{\text{eff},t} \cdot r_{\text{mkt},t} \;+\; \varepsilon_t.
$$
損失日で $|\varepsilon_t| > 1.5\sigma_\varepsilon$ などの条件を満たすと原因コード（EVT/REG/βMis/MOM/LQX…）を付与し、翌日から安全側アクション（$7$営業日で指数関数的減衰）を適用。

---

### 3.7 Adaptive Loop（Score/Beta）
**スコア再訓練（20日Ridge）**：SHAPドリフトが連続検知で
$$
\hat w \;=\; \arg\min_{w} \ \|y - Xw\|_2^2 \;+\; \lambda \|w\|_2^2,\quad (\lambda=0.2).
$$

**βリチューニング**：
$$
|\beta_{\text{eff}} - \beta^\*| > 0.1 \;\; \text{が3日連続} \;\Rightarrow\;
\beta^\* \leftarrow \max(0.2,\ \beta^\* - 0.2),\ \ Q_{\text{ETF}} \text{再設定}.
$$

**銘柄ローテ**：
$$
Z(S_i) > 2 \ \wedge\ \text{PnL}_i < -1\sigma \Rightarrow i \text{ を次点に交替}.
$$

---

### 3.8 Ensemble（NF×PR）
NF（統計平滑）と PR（痛み短期反映）を合成。ゲーティング変数 $g_t$（EventGuard, Breadth, GMI）から $\alpha_t \in [0,1]$ を決定：
$$
w_t \;=\; \alpha_t\, w_t^{\text{NF}} \;+\; (1-\alpha_t)\, w_t^{\text{PR}}.
$$

安全側ルール：
$$
\text{EG}_t=1 \Rightarrow \alpha_t = 0.9,\qquad
\text{BreadthPC1}_t \uparrow \Rightarrow \alpha_t \uparrow,\qquad
\text{GMI}_t \uparrow \Rightarrow (1-\alpha_t) \le 0.6.
$$

乖離キルスイッチ：
$$
\text{corr}(w^{\text{NF}}, w^{\text{PR}}) < 0.2 \Rightarrow \beta^\* = 0.2,\ (1-\alpha_t) \le 0.3.
$$

最終は共分散最適：
$$
\min_{\tilde w}\ \tilde w^\top \Sigma \tilde w
\quad \text{s.t.}\quad
\beta(\tilde w)=\beta^\*,\ \ \|\tilde w - w_t\|_1 \le \tau.
$$

---

### 3.9 Intraweek Overlay（週跨ぎ禁止）
週内（月〜金）のみ保有。金曜運用：
$$
t \ge \text{Fri 14:30} \Rightarrow \text{新規停止},\qquad
t \ge \text{Fri 14:50} \Rightarrow \text{全建玉クローズ}.
$$

平日内のオーバーナイト可否は、固定もしくは条件付VaRで判定：
$$
\text{VaR}_{1d}^{\text{overnight}} \le 1.5\% \Rightarrow \text{可},\quad
\text{（Event/祝前/金曜は常に不可）}.
$$

---

### 3.10 Multi-Horizon Ensemble（D × IW）
日次 $w^{(D)}$ とイントラウィーク $w^{(IW)}$ を
$$
w \;=\; \gamma \, w^{(D)} + (1-\gamma)\, w^{(IW)}.
$$
ゲート：EventGuard ON $\Rightarrow \gamma=0.8$、週内Breadth悪化 $\Rightarrow \gamma=0.6$。  
乖離キル：$\text{corr}(w^{(D)}, w^{(IW)})<0.3 \Rightarrow \beta^\*=0.2$、IW縮小。

---

### 3.11 Leverage Control（信用）
最大建玉倍率 $L_{\max} \in [2.0, 3.0]$。原資ベース1日VAR制約：
$$
\text{VaR}_{\alpha=99\%}(w,L) \;=\; z_{0.99}\, L\, \sqrt{w^\top \Sigma w} \;\le\; 2\%.
$$
β上限：
$$
\beta_{\text{eff}}(w,L) \;\le\; 0.9.
$$

レジーム別ガイド：
$$
(\text{BULL},\ \beta^\*=0.6,\ L\approx 2.5),\quad
(\text{NEUTRAL},\ \beta^\*=0.4,\ L\approx 1.8),\quad
(\text{DEF},\ \beta^\*=0.2,\ L\approx 1.2).
$$

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
- **WFA**：日次・IW個別→最終合成のWF評価  
- **検定**：SPA / MCS / Diebold–Mariano  
- **指標**：Sharpe, Calmar, MaxDD, 相関崩壊時挙動, β逸脱, 回転, コスト

---

## 6. 運用／RPA
- 現物＝**金額**発注、ETF＝**単元**発注  
- 監査：β逸脱・Event時刻・Post-Loss適用・維持率ログ  
- 祝前・金曜の強制フラット自動化（14:50成行）

---

## 7. スケジュール
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
> **Event（反射） × Regime（思考） × Post-Loss（学習） × Ensemble（NF×PR） × Intraweek（時間分散） × Leverage（資本効率）**  
> により「踏まない・負けにくい・早く立ち直る」AIトレーディング基盤を構築する。  
> 2026年Q1にPoC完了、Q2に量産運用フェーズへ。

---

© 2025 Souta Nakatani / MANUS Project

