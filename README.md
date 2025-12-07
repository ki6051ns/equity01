# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 2.4 / Updated: 2025-12-05**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

本システムは ALPHAERS（統合戦略）の中心に位置する **エクイティ戦略レイヤー**であり、  
**透明性・説明可能性・再現性（replicability）・堅牢性（robustness）** を最優先事項とします。

---

## 🚀 プロジェクトの到達点イメージ

equity01 が目指す姿：

- **black-box に依存しない透明なスコア駆動構造**
- **α/β の完全分離（relative α の定量・可視化）**
- **EventGuard によるイベントリスク遮断（ギャップ殺し）**
- **STOP Regime による中期下落局面の自動ガード**
- **β制御（インバースETF/キャッシュ）によるドローダウン縮小**
- **Multi-Horizon / Parameter Ensemble による α の安定化と強化**

最終的には、ALPHAERS 全体の内部で

> **エクイティ・モジュール（Equity Alpha Engine）として常時稼働**

することを目的とする。

---

## 🧱 アーキテクチャ構造（2025-12 Ver）

```text
equity01/
├─ data/
│   ├─ raw/              # 日次価格パネル（約94銘柄）
│   ├─ processed/
│   │   ├─ features/     # 特徴量
│   │   ├─ scores/       # スコア
│   │   ├─ portfolio/    # ポートフォリオ・日次リターン
│   │   ├─ guards/       # EventGuard / STOP regime
│   │   └─ stop_regime_plots/ # STOPタイムライン・戦略比較図
│   └─ calendar/         # 祝日・macro event カレンダー（event01）
│
├─ scripts/
│   ├─ build_features.py          # 特徴量生成
│   ├─ scoring_engine.py          # スコアリングエンジン
│   ├─ build_portfolio.py         # 日次ポートフォリオ構築
│   ├─ event_guard.py             # EventGuard v1.1
│   ├─ paper_trade.py             # バックテスト（Return標準化）
│   ├─ run_single_horizon.py      # H1〜H120 ラダーBT
│   ├─ compare_ladder_vs_baseline.py
│   ├─ calc_alpha_beta.py         # relative α算出
│   ├─ eval_stop_regimes.py       # STOP Regime + Plan A/B 評価
│   └─ ...
│
├─ features/   # feature builder modules
├─ models/     # Regime 判定（PCA/HMM など、将来実装）
├─ research/   # notebooks / 分析
└─ exec/       # 実行・デプロイ用スクリプト
🧪 実装状況スナップショット（Ver 2.4 / 2025-12）
🎯 今回アップデートのハイライト（8th → 13th commit）
8th_commit

EventGuard v1.1

must-kill イベント（FOMC / CPI / 雇用統計 / BOJ / SQ / 決算）の体系化

9th_commit

全モジュールの Return ベース標準化

calc_alpha_beta.py による relative α / β分離基盤

10th_commit

ラダー方式（non-overlap horizon） の本格導入

H1〜H120 の全ホライゾン比較 → H60/H90/H120 コア化

11th〜13th_commit

STOP Regime（中期下落検知ロジック）の実装

インバースETF/キャッシュを用いた Plan A / Plan B の比較

ベータに引きずられる負け（特に 2018, 2022 年）の抑制ロジックを確立

以下、モジュールごとに概要を整理する。

✅ EventGuard v1.1（8th_commit）
役割
「1日レベルのギャップ・イベントリスク」を遮断するガードレイヤー。

決算ギャップ・macroイベント・WE跨ぎ（Fri→Mon）を統合管理。

主な機能
must-kill イベント階層化

優先1：Macro ボライベント（FOMC / CPI / 雇用統計 / BOJ / メジャーSQ）

優先2：決算ギャップリスク

優先3：WE跨ぎ（Friday→Monday ギャップ）

EventGuard クラス API

get_excluded_symbols(date)

get_hedge_ratio(date)

inverse_symbol

decision_date (T-1)

trading_date (T)

ヘッジタイミングの標準化

前日引けでヘッジ構築 → 当日引けで解消

daily_portfolio_guarded.parquet に
hedge_ratio, inverse_symbol, decision_date, trading_date を記録。

→ event01（カレンダー情報）の parquet 化により、
決算除外＋macroヘッジの自動運転が可能な状態まで到達。

✅ Return標準化・α/β分離（9th_commit）
paper_trade v2：Returnベースへの完全統一
出力を PnL ではなく Return に統一：

daily_return

daily_return_alpha

daily_return_hedge

equity

drawdown

→ ALPHAERS 他ストラテジー（forex, future, parity, crypto 等）との
アンサンブル互換性（合成・比較）が確立。

calc_alpha_beta v2：relative α の可視化
ポートフォリオ CC return

TOPIX CC return

relative α（日次差分）を一括計算。

→ β 要素を完全に切り離した 純粋なαの測定基盤 を確立。
　equity01 の改善は、**「αを伸ばすか・βを抑えるか」**で議論可能になった。

✅ ラダー方式（non-overlap horizon）（10th_commit）
従来の問題：overlapping horizon の構造的欠陥
同一シグナル日に同一銘柄が複数ホライゾンで重複

α の過大評価

ノイズの増幅

実運用再現性の低下

→ クオンツとしては致命的なバイアス のため、構造から見直し。

解決：完全ラダー方式の導入
実装済ホライゾン：

H1 / H5 / H10 / H20 / H60 / H90 / H120

それぞれについて

非ラダー（従来）

ラダー（non-overlap）

を比較し、Sharpe / α / MaxDD を比較。

主要ホライゾン別の知見（要約）
Horizon	概要
H1	ラダー化でαが大きく減衰。過大評価が顕著 → ウェイト縮小。
H5	良好。曜日効果の残課題あり。補助ホライゾン候補。
H10	安定。H1 とセットで低比率採用。
H20	ラダー版でやや弱体化 → 使用ウェイトを抑制。
H60	ラダー版が Sharpe・累積とも大幅改善。
H90	最強クラス。Sharpe ≒ 0.73、相対α +130%。
H120	H90 に次ぐ強さ。Sharpe ≒ 0.72、相対α +123%。

結論：アンサンブル採用ホライゾン
グループ	ホライゾン	役割・方針
コア採用	H60 / H90 / H120	α源泉の主力。Sharpe > 0.70 クラス。
サブ採用	H5 / H10	週内効果を補完するため少量採用。
抑制	H1 / H20	ノイズ多め。ウェイト小さく限定利用。

→ 「安定性＋再現性＋汎用性」が大幅に改善。
　後続の Multi-Horizon Ensemble の土台が完成。

✅ STOP Regime & Plan A/B（11th〜13th_commit）
目的
「ベータに引きずられて負ける年（2018, 2022）をどう抑えるか」

を、ルールベースで制御するレイヤー。

STOP0

ポジションをゼロ（ノーポジ）にする単純STOP

Plan A

インバースETF（TOPIXベア）を用いた 弱ショートベータ戦略

Plan B

キャッシュ（現金化）を併用する 保守的ベータ縮小戦略

STOP シグナルの定義（初期版）
eval_stop_regimes.py にて：

cross4 の 60日 / 120日ローリングリターン を用いて
「中期的な下落局面」を検知。

サンプル全体での STOP 期間：

60d: 286日（全体の 11.8%）

120d: 224日（全体の 9.3%）

→ 過度な頻度ではなく、「明らかな調整局面」で点灯している。

STOP0（ノーポジ戦略）の評価
Baseline cross4

累積 +269% / 年率 +14.6% / MaxDD -32.7%

STOP0 60d

累積 +216% / 年率 +12.7% / MaxDD -19.8%

STOP0 120d

年率 +9.8% / MaxDD -25.7%

示唆：

ドローダウン改善は大きいが、
リターン側の犠牲も大きく、旗艦としては物足りない。

「キャピタル保全を最優先するモード」の fallback 戦略として有用。

Plan A：STOP中「cross4 75% + inverse 25%」
最終的に採用候補とした構造：

STOP期間 外：cross4 100%

STOP期間 中：cross4 75% + TOPIXインバース 25%
（合計エクスポージャは常に 100%）

→ ベータを完全に中立にするのではなく、
　「やや弱いロングベータ」まで抑制するイメージ。

Plan A 60d（メイン候補）の結果：

累積：+456%

年率：+19.6%（cross4: +15.0%）

年率α：+9.78%（cross4: +5.17%）

αシャープ：1.05（cross4: 0.74）

MaxDD：-21.8%（cross4: -32.7%）

年間勝率：90%

Plan A 120d：

年率 +17.7% / 年率α +8.12% / αシャープ 0.78 / MaxDD -27.6%

→ リスクを大きく抑えながら、リターンとαをむしろ押し上げる
　バランスの良いストラテジーとなっている。

Plan B：STOP中「キャッシュ 50%」
構成：

STOP期間外：cross4 100%

STOP期間中：cross4 50% + cash 50%

Plan B 60d：

累積 +248% / 年率 +13.9%

年率α +4.17% / αシャープ 0.86

MaxDD -21.1%

Plan B 120d：

年率 +12.7% / MaxDD -27.9% / αシャープ 0.41

→

ロジックが非常にわかりやすい

ベータ縮小効果が明確
という意味で、ディフェンシブ運用時のバックアップ STOP 戦略として有効。

STOP Regime レイヤーの位置付け
Plan A 60d
→ equity01 の 標準 STOP ガード候補（本線）

Plan B 60d
→ より保守的な運用モード時の オプションガード

今後は

期間分割（2016–2019 / 2020–2025）による In-Sample / OOS 検証

STOP中ウェイト（90/10, 80/20, 70/30 など）のロバスト性テスト

コスト・スプレッド・指数乖離を加味した実運用レベルのシミュレーション

を通して、ALPHAERS 全体の標準レイヤーとして確定させていく。

📌 現在までに完成している要素（2025-12）
94銘柄ユニバース（流動性上位約20％）

parquet データ基盤

Feature Builder（ret / vol / ADV / heat_flag など）

Scoring Engine v1.1（サイズバケット正規化）

EventGuard v1.1（macro / 決算 / WE跨ぎ）

daily_portfolio_guarded 出力

paper_trade v2（Return 統一）

Ladder Backtest（H1〜H120）

calc_alpha_beta（relative α）

STOP Regime 基盤（STOP0 / Plan A / Plan B）

STOP timeline & strategy comparison plots

🔮 今後のロードマップ（2026 まで）
🟣 Multi-Horizon Ensemble（次フェーズ）
採用ホライゾン：H60 / H90 / H120（コア）＋ H5/H10（サブ）

重み付け例：

text
コードをコピーする
final_weight
  = w_H60 * a
  + w_H90 * b
  + w_H120 * c
  + small_mix(H5, H10)
a, b, c は Sharpe / α / MaxDD に基づく最適化も視野。

🟣 パラメータアンサンブル（zscore × score）
スコアリングの二本立て：

zscore ベース

生スコア / 別指標ベース

合成イメージ：

text
コードをコピーする
w_final = (1 - λ) * w_z + λ * w_s
トレンド相場：λ を大きく（score 強め）

ノイズ相場：λ を小さく（zscore・リバランス抑制）

→ Regime 判定と連動させることで、動的パラメータアンサンブルへ拡張。

🟣 Regime 判定（2026Q2 〜）
Breadth PCA（市場内部の広がり・偏り）

HMM / Sticky-HMM によるレジーム分類

Regime に応じた重み調整：

βレバー（Plan A/B 強度）

ホライゾンウェイト（H60/H90/H120の配分）

λ（zscore vs score）

🟣 EventGuard v0.3 以降
225先物（5分変動）

USDJPY（σ距離）

VIX

ニュース速報（event02）＋ LLM 要約評価

簡易 VAR によるリスク上限

📂 実行コマンド（標準フロー）
bash
コードをコピーする
# 特徴量生成
python scripts/build_features.py

# ポートフォリオ構築（単一ホライゾン）
python scripts/build_portfolio.py

# 単一ホライゾン・ラダーバックテスト
python scripts/run_single_horizon.py 60   # 例: H60

# ペーパートレード（Return出力）
python scripts/paper_trade.py

# α/β 分離・relative α 計算
python scripts/calc_alpha_beta.py

# STOP Regime + Plan A/B 評価
python scripts/eval_stop_regimes.py
📝 所感（Ver 2.4 時点）
10th_commit までで 「再現性あるα抽出」 の土台が整い、

11th〜13th_commit で 「いつフルベータを取らないか」 というレジーム制御が加わった。

特に Plan A（STOP中 75% cross4 + 25% inverse）は、

ドローダウンを 10pt 以上圧縮しつつ

年率リターンと年率αを同時に押し上げる

という、戦略として非常に魅力的なポジションを獲得している。

今後、ホライゾンアンサンブルとパラメータアンサンブル、Regime 判定を統合し、
STOP Regime / EventGuard を上位レイヤーとして噛ませることで、

2026 Q1〜Q2 に「ALPHAERS 初期版」の中核エクイティモジュール

として完成させるロードマップが、かなり現実的なフェーズに入った。

Prepared by equity01 / Strategy Core Layer
Research Plan v2.4（8th ～ 13th commit を反映）
