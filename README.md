



'''
equity01/
│
├─ data/
│   ├─ raw/                # 株価・出来高・為替・VIX・先物など生データ
│   ├─ calendar/           # 祝日・イベントカレンダー（BOJ/FOMC/CPI等）
│   ├─ processed/          # クレンジング後データ（日次・週次）
│   └─ interim/            # 一時保存（特徴量中間生成物など）
│
├─ features/
│   ├─ momentum/           # 短中期リターン・加速度
│   ├─ breadth/            # 上昇/下落比率・新高値率など
│   ├─ fa_quick/           # EPS改定・ROIC・FCFマージン
│   ├─ volatility/         # σ・ATR・回転率
│   └─ gmi/                # 米株→日株モメンタム指標（S&P/VIX/USDJPY）
│
├─ models/
│   ├─ regime/             # HMM・BOCPD・Logit
│   ├─ scoring/            # Ridge/Lasso/Tree系スコアリング
│   ├─ event_guard/        # イベント検知モデル
│   └─ ensemble/           # NF×PR統合モジュール
│
├─ exec/
│   ├─ backtest/           # バックテスト出力（PnL, trades, βなど）
│   ├─ live/               # ペーパートレード（orders_YYYYMMDD.csv）
│   └─ audit/              # 監査ログ・Post-Loss原因コード
│
├─ research/
│   ├─ notebooks/          # 分析用ノートブック（EDA, WF, Ensemble検証）
│   ├─ reports/            # KPI・MCS・回転・相関レポート
│   └─ config/             # ハイパーパラメータ・閾値設定
│
└─ scripts/
    ├─ data_loader.py
    ├─ feature_builder.py
    ├─ regime_engine.py
    ├─ event_guard.py
    ├─ portfolio_optimizer.py
    ├─ execution_simulator.py
    └─ post_loss_analyzer.py
'''





# AI駆動・日本株インテリジェント日次トレーディングシステム 研究開発計画書 Ver.1.6
### ― モメンタム×クイックFA＋Breadth PCA＋HMM＋EventGuard＋Intraweek＋Leverage ―

---

## 1. 背景と目的

従来の裁量・高速依存型デイ戦略では汎用性・安定性・再現性に乏しい。  
現物・信用を併用しつつ、AIによるレジーム制御とイベント防御を備えた**日次完結型トレーディング基盤**を構築する。  
OOS（Out-of-Sample）で統計的有意なα（t>2）と Sharpe ≥ 0.9 を確認し、完全自動（RPA）＋SLA管理下で稼働可能なフレームを実装する。

---

## 2. 成功指標（KPI）

| 区分 | 指標 | 目標値 |
|---|---|---|
| リターン | 年率リターン（原資基準） | ≥ 15–20% |
| リスク調整 | Sharpe | ≥ 0.9 |
| 安定性 | Calmar | ≥ 0.6 |
| テールリスク | 下位5%日損益 | ≥ −0.5%以内 |
| 運用安定性 | 夜間SLA達成率 | 100%（連続10営業日） |
| レバ管理 | 1日VAR（原資基準） | ≤ 2% |
| EventGuard遅延 | 平均 ≤ 10分、最大 ≤ 30分 |
| Post-Loss反応 | 翌日適用率 100% |

---

## 3. 戦略構成

### 3.1 銘柄スコアリング

- **ユニバース**：東証流動性上位20％  
- **特徴量**：短中期モメンタム、出来高加速、強さ指標、過熱抑制、低ボラ、クイックFA（EPS改定・ROIC 等）  
- **合成**：分位スコア＋ペナルティ（過熱／スプレッド／ADV）  
- **配分式**：  
  \[
  w_i \propto \frac{(Score_i^+)^\alpha}{\sigma_i^\beta} \quad (\alpha=1.0,\ \beta=0.5)
  \]
- **セグメント均等**：Large/Mid/Small = **1/3ずつ**  
- **βドミナンス制約**：\(|β_i|·w_i ≤ 0.05\)  
- **Breadth補完**：相関一様化時に分散項を目的関数へ加重

---

### 3.2 β制御（現物＋ETF階段）

- **β目標**：0.6 / 0.4 / 0.2（強気 / 中立 / 防御）  
- **実装**：ETFで階段（単元発注）、現物は未満株で補間（連続近似）  
- **実効β**：  
  \[
  β_{eff} = β_{long} - β_{ETF}\cdot(Q_{ETF}/NAV)
  \]
- **逸脱対応**：|Δβ| > 0.1 で β Retune（目標段下げ＋ETF±1単元）

---

### 3.3 レジーム判定（思考層｜日〜週）

- **モデル**：Breadth PCA ＋ Sticky-HMM ＋ BOCPD ＋ Rule-Logit  
- **検出**：R ≥ θH → 強気、R ≤ θL → 防御（ヒステリシス）  
- **安全装置**：Breadth −2σ 新規停止、−3σ 撤退  
- **WF**：学習 180 日／運用 60 日、最小滞在 5 日、PSI 監視

---

### 3.4 EventGuard（反射層｜秒〜時間）

- **トリガー例**：
  - 先物 5 分リターン ≤ −1.0%
  - USDJPY 10 分変化 ≥ 1.5σ（円高方向は厳格）
  - VIX 30 分 +10%
  - 重要度 ≥ 4 のイベント（BOJ/FOMC/CPI/NFP 等）
- **作動**：新規停止＋引成クローズ、β = 0.2、通知（Slack/LINE）  
- **継続**：最低 5 営業日。解除は Breadth 改善連続 4 日で  
- **SLA**：発動遅延 平均 ≤ 10 分、最大 ≤ 30 分

---

### 3.5 GMI（Global Momentum Index｜米株⇒日株）

\[
GMI = 0.5\cdot Z(S\&P\ 先物) + 0.3\cdot Z(VIX^{-1}) + 0.2\cdot Z(USDJPY)
\]

- 8:00 時点で算出。**GMI > 0.5** → 強気寄り、**< −0.5** → 防御寄り  
- イベント前後（±1日）は **無効化**（EventGuard優先）

---

### 3.6 Post-Loss Learning（翌日反映）

- **原因コード**：EVT / REG / βMis / MOM崩壊 / LQX / CEX などを自動付与  
- **翌日からの安全側アクション（7 日で指数関数的に復帰）**：
  - EVT：閾値強化、重要度格上げ、GMI ブラックアウト延長
  - βMis：β 目標 −0.2、ETF ±1 単元補正
  - MOM 崩壊：モメ重み −30%、低ボラ加点、建玉縮小
  - LQX：ADV 上限 1.5%、スプレッド罰則強化
- **反実仮想**：ノートレ／β=0.2／モメ縮小を生成 → 週次の A/B で採択

---

### 3.7 Adaptive Loop（Score–Beta）

- **Score Drift**：SHAP ドリフト > 1.5σ × 3 日 → **20 日 Ridge 再訓練**  
- **β Drift**：|βeff − βtarget| > 0.1 × 3 日 → **βRetune**（目標段下げ＋HMM 閾値微調整）  
- **銘柄ローテ**：スコア Z > 2 かつ PnL < −1σ → 次点銘柄に交替  
- **頻度**：日次 Quick-Fit／週次 Full-Fit／月次 Feature 再選抜

---

### 3.8 Ensemble（NF × PR）

- **NF（Noise-Filtered）**：痛みは記録のみ、週次で統計反映（安定・低回転）  
- **PR（Pain-Responsive）**：痛みを短期に**安全側**へ反映（縮小・ペナルティ中心）  
- **ゲーティング**：
  - EventGuard = ON → w_NF = 0.9、w_PR = 0.1
  - Breadth PC1 高（≥ 0.8）→ NF 寄せ
  - GMI 強気・平常相関 → PR 最大 0.6 まで許容
- **乖離キルスイッチ**：corr(w_NF, w_PR) < 0.2 → βtarget = 0.2、PR 上限 0.3  
- **仕上げ**：共分散最適化（β制約・回転上限 τ=0.06）

---

### 3.9 Intraweek Overlay（週跨ぎ禁止｜IW）

- **運用範囲**：月〜金の**週内完結**。週末・祝前日は**完全クローズ**  
- **β**：0.5 / 0.35 / 0.2（強気／中立／防御）  
- **金曜運用**：14:30 新規停止、14:50 強制フラット  
- **Event/祝前**：新規禁止＋β = 0.2

**Overnight（平日内のみ）**

| 区間 | 可否 | 代表シグナル |
|---|---|---|
| 月→木 間 | 可 | 低ボラ・決算ドリフト・GMI 追随 |
| 木→金 | 条件付可 | Event/祝前は不可 |
| 金→月 | **禁止** | — |

**適性管理**

- **固定型**：低ボラ・Quality・決算ドリフト・セクター相対強度・GMI 追随 = 可／デイ・リバーサル・ギャップ回帰 = 不可  
- **動的型**：同セクター×同レジーム×同 GMI 帯で VaR < 1.5% なら可（当面は Shadow 運用）

---

### 3.10 Multi-Horizon Ensemble（D × IW）

\[
w = \gamma\, w^{(D)} + (1-\gamma)\, w^{(IW)}
\]

- **ゲート**：EventGuard = ON → γ = 0.8／週内 Breadth 悪化 → γ = 0.6／木曜後半・祝前 → IW 縮小  
- **乖離時**：corr(D, IW) < 0.3 → β = 0.2、IW 縮小  
- **仕上げ**：共分散最適化（β制約・L1 近接 τ=0.06）

---

### 3.11 Leverage Control（信用 2–3 倍）

- **最大建玉倍率**：2.0–3.0×（現物＋信用）  
- **原資 1 日 VAR ≤ 2%**, **βcap = 0.9**  
- **Event 週**：自動で 1.0× 上限  
- **維持率 60% 警戒**：即時縮小（RPA 通知）

**レジーム別レバ例**

| レジーム | β目標 | 想定レバ |
|---|---|---|
| 強気 | 0.6 | 2.5x |
| 中立 | 0.4 | 1.8x |
| 防御 | 0.2 | 1.2x |

**YAML 例**

```yaml
leverage:
  enable: true
  gross_limit: 2.5
  net_beta_cap: 0.9
  capital_risk_limit: 0.02   # 原資1日VAR
  stop_trigger_sigma: -2.5
```

---

## 4. データ／分析構成

```
/data/raw            (prices, volume, fx, vix, futures, calendar)
/data/weekly_raw     (週次終値・為替)
/feature             (momentum, breadth, fa_quick, gmi)
/feature/weekly      (mom20/60/120, breadth_w, fa_quick_w)
/labels              (regime, event_flags)
/models              (score_v*, hmm_v*, ridge_lasso_)
/exec                (orders_YYYYMMDD.csv, audit_logs)
/ops                 (event_days.csv, runbooks)
/research            (backtest, param_grid, spa_mcs, shadow_runs)
```

---

## 5. 検証

- **比較モデル**：逆ボラ／EW／最小分散／短中期 MOM／低ボラ／VolTarget／Overnight/Intraday／βヘッジ（計 15 本）  
- **WFA**：日次・IW を個別に WF → 最終合成を評価  
- **統計**：SPA／MCS／Diebold–Mariano（OOS のみ採点）  
- **レポート**：Sharpe, Calmar, MaxDD, 相関崩壊期挙動, 回転, コスト, β逸脱

---

## 6. 運用／RPA 実行

- **現物＝金額発注（未満株）**, **ETF＝単元発注**  
- `orders.csv` 例：

```
ticker,mode,value,volume,notes
7203,amount,180000,,stock
1571,shares,,100,etf_inverse
```

- **監査**：実効β、Event 発動時刻、Post-Loss 適用ログを保存（スクショ＋CSV）

---

## 7. ガバナンス

- 日次変更は**原因コード**に紐付く軽微調整のみ  
- 週次で構造更新（モデル再学習・閾値調整）  
- データ保全：BitLocker＋Git-LFS、再現率 ≥ 95%  
- 監査項目：Event／β逸脱／PnL 分解／ペイン統計／A/B 影運用結果

---

## 8. 開発スケジュール

| Phase | 内容 | 期間 |
|---|---|---|
| P0 | MANUS環境構築・Git連携 | 〜 11/10 |
| P1 | 日次 Feature 実装 | 〜 11/17 |
| P2 | HMM ＋ EventGuard 稼働 | 〜 11/24 |
| P3 | Adaptive ＋ NF×PR 統合 | 〜 12/05 |
| P4 | Intraweek ＋ Multi-Horizon | 〜 12/20 |
| P5 | PoC ペーパートレード（10 営業日） | 1 月 |
| P6 | Fat-Trim（特徴削減・回転抑制） | 2 月〜 |

---

## 9. 成果物

- Python 3.11 ソース一式（MANUS 連携）  
- `orders_YYYYMMDD.csv`／`event_days.csv`  
- KPI／MCS／Latency／Leverage レポート  
- PoC 報告書、運用手順書（EventGuard／Ensemble／Intraweek）

---

## 10. 結論

> **EventGuard（反射） × RegimeGuard（思考） × Post-Loss（学習） × Ensemble（NF×PR） × Intraweek（時間分散） × Leverage（資本効率）**  
> 現物×信用×AI統合により「踏まない・負けにくい・早く立ち直る」日本株日次アルゴを実現する。  
> 2026年1月までに PoC を完了し、同年第2四半期に量産運用フェーズへ移行予定。
