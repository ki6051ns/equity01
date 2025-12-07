# equity01: AI駆動・日本株インテリジェント日次トレーディングシステム  
**Version 2.5 / Updated: 2025-12-06（dev フェーズ完了版）**

equity01 は **AI駆動 × 正統クオンツ**によって構築された  
日本株向け **インテリジェント日次トレーディングシステム**です。

ALPHAERS（統合戦略）の中核である **Equity Strategy Layer** を担い、  
**透明性・説明可能性・再現性・堅牢性** を最優先に設計されています。

本バージョン（v2.5）は  
**8th〜13th commit の開発を正式にクローズ**し、  
**dev → prod 移行の最終到達点** を示します。

---

# 🚀 1. プロジェクト到達点（devフェーズ完了判定）

equity01 は現在、以下の5点をすべて満たし、**実運用可能な水準に到達**した。

## **① 再現性ある relative α の安定抽出**
- H60 / H90 / H120 のラダーホライゾンで  
  **Sharpe > 0.70、α累積 +120〜130%** の持続的な α を確認  
- Return-based パイプラインの統一により  
  ALPHAERS 全体と合成可能な形式へ移行

## **② EventGuard v1.1 による“ギャップ殺し”構造の確立**
- FOMC / CPI / 雇用統計 / BOJ / SQ / 決算を統合管理  
- 銘柄除外＋インバースヘッジが自動運転化  
- 実運用に耐える「決算 × macro × WE跨ぎ」の三層構造

## **③ STOP Regime（Plan A/B）の実装とロバストネステスト完勝**
STOP Regime の目的：  
**「ベータに引きずられて負ける年（2018・2022）を抑制」**

徹底的な検証を実施し、**全テストで合格**：

- IS/OOS（2016–19 / 2020–25）で性能崩れなし  
- STOP中ウェイト（90/10〜60/40）で単調なロバスト性  
- コスト込みでも α が残り、DD改善を維持  
- 2016/2018/2020/2022 の全イベントで均等に寄与  
- 単純STOP（TOPIX 60d < 0）でも方向性が一致

→ **Plan A：STOP中 75% cross4 + 25% inverse（60d）  
＝ equity01 標準 STOP ガードとして正式採用**

## **④ リスクの実運用水準への落とし込み完了**
Plan A（60d）：  
- 年率 +19.55%（cross4: +14.6%）  
- αシャープ 1.05  
- MaxDD -21.8%（cross4: -32.7%）

**DD・α・βの三要素がすべて“壊れない”構造を獲得。**

## **⑤ メンテナンス性の確保（3/6/12ヶ月サイクル）**
STOP Regime の  
“壊れ方・検知ポイント・修復方法” が完全に固定化。

→ **戦略を「長寿命パーツ」として運用可能なフェーズへ到達。**

---

# 🧱 2. アーキテクチャ概要（2025-12 Dev Closure）

```text
equity01/
├─ data/
│   ├─ raw/                # 日次価格（TOPIX浮動株比重で抽出した94銘柄）
│   ├─ processed/
│   │   ├─ features/       # 特徴量
│   │   ├─ scores/         # スコア
│   │   ├─ portfolio/      # 日次ポートフォリオ
│   │   ├─ guards/         # EventGuard / STOP Regime
│   │   └─ stop_regime_plots/
│   └─ calendar/           # macro / earnings calendar
│
├─ scripts/
│   ├─ build_features.py
│   ├─ scoring_engine.py
│   ├─ build_portfolio.py
│   ├─ event_guard.py               # EventGuard v1.1
│   ├─ paper_trade.py               # Return-based BT
│   ├─ run_single_horizon.py        # ラダーBT
│   ├─ calc_alpha_beta.py           # 相対α分離
│   ├─ eval_stop_regimes.py         # STOP評価
│   └─ eval_stop_regimes_robustness.py # dev最終ロバスト性テスト
│
├─ features/
├─ models/          # Regime判定（PCA/HMM予定）
├─ research/
└─ exec/
🧪 3. 8th〜13th commit の成果総括（dev フェーズの確定ログ）
8th_commit – EventGuard v1.1
macro/決算/WE跨ぎを階層化

inverseヘッジと銘柄除外の二段式

ヘッジ時点を「前日決定 → 当日実行」に統一

9th_commit – Return標準化 & α/β分離
全処理を Return ベースに統一（PnL→Return）

relative α / β 分離を完全実装

他ストラテジー（forex/future/parity）との合成基盤を確立

10th_commit – ラダー方式（non-overlap horizon）
H60/H90/H120 が αコアとして確立

H5/H10 を補助ホライゾンとして採用

H1/H20 は抑制（ノイズ・過大評価が顕著）

＝ Multi-Horizon Ensemble の基礎構築完了

11th〜13th_commit – STOP Regime（Plan A/B）
STOP Regime の目的：
「中期下落 × β暴走」を抑制して DD を縮小すること

Plan A：cross4 75% + inverse 25%（標準ガード）

Plan B：cross4 50% + cash 50%（保守ガード）

全ロバストネステスト完勝（IS/OOS/コスト/イベント/単純化）

＝ STOP Regime は equity01 の正式ユニットとして採用

🧱 4. Devフェーズ総合判定（v2.5）
検証項目	結果
IS/OOSテスト	合格：OOS で DD改善＋α維持
STOPウェイト	合格：特異点なし、単調トレードオフ
コスト評価	合格：αが残り DD改善も維持
イベント分析	合格：4イベントで均等寄与
単純STOP	合格：構造的一貫性あり
メンテ性	合格：3/6/12ヶ月の保守体系確立

→ equity01 dev フェーズは正式終了
→ 次 commit（14th）は prod transition commit

🔧 5. STOP Regime（Plan A）仕様（正式版 / v1.0）
Regime Condition（採用）
cross4 の 60日ローリングリターン

中期下落局面のみ STOP ON

Positioning
STOP OFF：cross4 100%

STOP ON：cross4 75% + TOPIX inverse 25%

設計思想
β完全中立ではなく
「弱ロングβ」まで抑える現実的なガード

役割
equity01 の 標準安全ユニット（βダンパー）

旗艦ポートフォリオの巨大βロングに対するショック吸収材

🔄 6. 今後のロードマップ（prod フェーズ / 2026〜）
① Multi-Horizon Ensemble（H60/H90/H120）
Sharpe/α/MaxDD に基づく動的ウェイト最適化。

② パラメータアンサンブル（zscore × score）
λ 制御による regime-based パラメータブレンディング。

③ Regime 判定（2026Q2〜）
Breadth PCA / Sticky-HMM / BOCPD
→ STOP やホライゾン・λ・βレバーを動的制御。

④ EventGuard v0.3
225先物5分・USDJPY σ距離・LLMニュース要約・簡易VAR。

⑤ prod-ready Pipeline
スケジューラ（AM7:30/PM15:00）

IBKR（国内）API連携

score drift / beta drift / STOP騙し率モニタリング

📝 7. 所感（Dev Closure）
equity01 は
「日次の安定α × β制御 × イベント遮断」 を同時に達成し、
実運用可能な 堅牢かつ長寿命な戦略パーツ へと進化した。

特に Plan A（STOP中 75% + inverse 25%） は、

DD を 10pt 以上圧縮

α を 2倍級に拡張

かつ壊れ方が予測でき

修理も容易

という極めて優秀な βガードユニットである。

本日のロバストネステスト合格により
equity01 dev は完全に終了し、
次フェーズは prod（統合・運用・強化） へと移行する。

Prepared by
equity01 / Strategy Core Layer
Research Plan v2.5（dev フェーズ完了版 / Updated 2025-12-06）
