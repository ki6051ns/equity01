📘 AI駆動・日本株インテリジェント日次トレーディングシステム
研究開発計画書 Ver.2.0（Markdown版）
― モメンタム×クイックFA＋Breadth PCA＋HMM＋EventGuard＋Intraweek＋Leverage ―
0. 開発体制と位置付け（Ver.2.0で新設）
0.1 開発スタック

ChatGPT：設計・要件定義・体系化担当

Cursor（無料→有料検討）：実装補助・GitHub連携

Claude：コードレビュー・監査専任

VSCode / Jupyter：ローカル実行環境

GPT ⇄ Cursor ⇄ GitHub ⇄ Claude の分業で開発コストを最小化する構造

0.2 開発フェーズ（現在位置）
分析 → 要件定義 → 外部設計 → 内部設計 → ■コーディング（今ここ）
       → コードレビュー → 単体テスト → 結合テスト → システムテスト → ベータ運用


equity01 = 日本株・日次・ロング軸の単体戦略

将来、equity02／forex01／crypto01 と共に ALPHAERS（統合PF） へ接続する基礎ユニット

1. 背景と目的

現物×信用に AI のレイヤー（RegimeGuard, EventGuard, Post-Loss）を重ね、
「踏まない・負けにくい・回復の早い」日本株アルゴを構築する。

目標：Sharpe ≥ 0.9、Calmar ≥ 0.6、OOS α（t>2）

毎日完結型（日次確定）

SLA・監査可能な実装

2. 成功指標（KPI）
区分	指標	目標値
リターン	年率 ≥ 15〜20%	
Sharpe	≥ 0.9	
Calmar	≥ 0.6	
テール	下位5%日損益 ≥ −0.5%	
運用安定性	夜間SLA 100%×10営業日	
EventGuard	遅延 ≤ 10分（最大30分）	
レバ	VAR ≤ 2%	
3. 戦略構成（ロジック全体）

以下は equity01 の全ロジックレイヤー。
Ver.2.0 では 3.1 銘柄スコアリングまで実装済み。

3.1 銘柄スコアリング（Ver.2.0で実装完了）
✔ ユニバース（実装済）

東証流動性上位20％

universe_builder.py → YYYYMMDD_universe.parquet

✔ 価格データ（実装済）

download_prices.py

yfinance / Stooq fallback

JST 換算 & MultiIndex 正規化

✔ 特徴量（実装済）

ret_1 / ret_5 / ret_20

vol_20

Zスコア

ADV

strength / heat_flag

✔ スコア合成（実装済）
w_i ∝ (Score_i^+)^α / σ_i^β
(α=1, β=0.5)

✔ Top10 出力（実行済）

run_scoring.py → Top10銘柄（penalized score順）

3.2 β制御（ETF階段＋現物補間）

※ 設計完了・実装前

β目標：0.6 / 0.4 / 0.2

ETF：単元ごとに階段

現物：未満株で連続補間

|Δβ| > 0.1 → β Retune

3.3 レジーム判定（思考層）
✔ モデル

Breadth PCA

Sticky-HMM

BOCPD

Rule-Logit

❗ Ver.2.0の重大方針（明確化）

レジーム判定ロジックは equity01 から切り出し、
ALPHAERS（統括PF側）の “グローバルレジームエンジン” へまとめて統合する。

理由

戦略ごとに個別レジームを持つと 整合性が壊れる

マルチストラテジー統合時に β・EventGuard・パリティが衝突

equity01 のみのローカル判定は後工程の 混線リスクが大きい

レジームは「全体の最終仕上げ」レイヤーであり、戦略単体では扱わない方が正しい

運用方針（Ver.2.0）

equity01 は neutral 固定

β制御はミニマム版

EventGuard だけは（局所防御）例外で搭載可能

3.4 EventGuard（反射層）

※ 設計完了・実装は β制御後

3.5 GMI（米株 → 日株）

※ 設計完了・実装前

3.6 Post-Loss Learning
3.7 Score–Beta Adaptive
3.8 NF×PR Ensemble
3.9 Intraweek Overlay
3.10 Multi-Horizon Ensemble
3.11 Leverage Control

※ すべて 設計完了 / 実装前

4. データ／システム構成
equity01/
├─ configs/
├─ data/
│   ├─ raw/
│   ├─ intermediate/universe/
│   ├─ processed/
│   └─ calendar/
├─ features/
├─ models/
├─ exec/
├─ research/
└─ scripts/


Ver.2.0 現在：DataLoader／Universe／Scoring が完成し、下層が完全稼働。

5. 検証（Ver.2.0明文化）
5.1 カットオフ政策の検証（必須）

08:00 JST 統一カットオフの妥当性

D-1補正との比較

DM統計・Sharpe差分で最適化

5.2 比較モデル

逆ボラ

EW

最小分散

MOM系多数

βヘッジ

Overnight / IW

5.3 テスト＝説明可能性の検証（重要）

テストが 合格となる条件：

市場環境・イベントを踏まえ 判断理由を説明できる

勝因・敗因を言語化 できる

説明と結果が 整合

説明不能は 改良対象（先送り禁止）

説明できるまでが単体テストの完了条件
— レジーム統合以前の最重要QA項目。

6. 開発プロセスと ALPHAERS との接続
6.1 equity01 = 単体テスト

ペーパートレードは equity01 ローカルの単体テスト

ロジック破綻・データ破綻の確認

説明可能性の担保

6.2 ALPHAERS = 結合テスト／システムテスト

全ストラテジー（equity, forex, crypto etc.）の相関・β・EventGuardを統合

レジーム判定は ALPHAERS 側で一元管理

パリティ配置も ALPHAERS が担当

equity01 の β制御だけ独立稼働 → 最終的に統合予定

6.3 ベータ運用（2026 Q1〜）

手動運転＋準自動（RPA）

SLA・監査ログを構築

Event／β逸脱／Post-Loss対応を定期検証

7. 開発スケジュール
Phase	内容	状態
P1	DataLoader / Universe	完了
P2	Feature & Scoring	完了
P3	β制御・cutoff_policy	これから
P4	EventGuard / GMI	設計済
P5	IW / Multi-Horizon	設計済
P6	Leverage / Post-Loss	後続
P7	PoC ペーパー運用	2026
P8	Fat-Trim	2026
8. 成果物

Python ソース一式

universe parquet

prices csv

scores parquet（予定）

orders.csv / audit

PoC 報告書

運用手順書

9. 結論

EventGuard × RegimeGuard × Post-Loss × Ensemble × IW × Leverage
により、「踏まない・負けにくい・回復の早い」日本株アルゴが成立する。

Ver.2.0 の到達点：

データ基盤 → ユニバース → スコアリング
までを正式に実装完了。

これにより β制御・EventGuard 以降の “戦略ロジック中核フェーズ” に進める状態となった。

レジーム判定は equity01 から切り出し、ALPHAERS に統合する方針を確定。
