---
layout: default
title: AI駆動・日本株インテリジェント日次トレーディングシステム Ver.1.61
---

<!-- MathJax読み込み -->
<script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
<script id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
</script>

# AI駆動・日本株インテリジェント日次トレーディングシステム 研究開発計画書 Ver.1.61
### ― モメンタム × クイックFA ＋ Breadth PCA ＋ HMM ＋ EventGuard ＋ Intraweek ＋ Leverage ―

---

## 1. 背景と目的

従来の裁量・高速依存型デイ戦略では汎用性・安定性・再現性に乏しい。  
現物・信用を併用しつつ、AIによるレジーム制御とイベント防御を備えた**日次完結型トレーディング基盤**を構築する。  
Out-of-Sample（OOS）で統計的有意な $\alpha$（$t > 2$）と $\text{Sharpe} \geq 0.9$ を確認し、完全自動（RPA）＋SLA管理下で稼働可能なフレームを実装する。

---

## 2. 成功指標（KPI）

| 区分 | 指標 | 目標値 |
|---|---|---|
| リターン | 年率リターン（原資基準） | $\geq 15\% \sim 20\%$ |
| リスク調整 | Sharpe | $\geq 0.9$ |
| 安定性 | Calmar | $\geq 0.6$ |
| テールリスク | 下位5%日損益 | $\geq -0.5\%$ 以内 |
| 運用安定性 | 夜間SLA達成率 | $100\%$（連続10営業日） |
| レバ管理 | 1日VAR（原資基準） | $\leq 2\%$ |
| EventGuard遅延 | 平均 $\leq 10$ 分、最大 $\leq 30$ 分 |
| Post-Loss反応 | 翌日適用率 $100\%$ |

---

## 3. 戦略構成

### 3.1 銘柄スコアリング



\[
w_i \propto \frac{(Score_i^+)^\alpha}{\sigma_i^\beta} \quad (\alpha=1.0,\ \beta=0.5)
\]





\[
|β_i| \cdot w_i \leq 0.05
\]



---

### 3.2 β制御（現物＋ETF階段）



\[
β_{\text{eff}} = β_{\text{long}} - β_{\text{ETF}} \cdot \left(\frac{Q_{\text{ETF}}}{NAV}\right)
\]



---

### 3.3 レジーム判定（思考層｜日〜週）

Breadth PCA、Sticky-HMM、BOCPD、Rule-Logit による複合判定。  
ヒステリシス制御、Breadth −2σ停止、−3σ撤退、安全装置付き。

---

### 3.4 EventGuard（反射層｜秒〜時間）

イベントトリガー例：

- 先物5分リターン $\leq -1.0\%$
- USDJPY10分変化 $\geq 1.5\sigma$
- VIX30分変化 $+10\%$
- BOJ/FOMC/CPI/NFP 等の重要イベント

---

### 3.5 GMI
