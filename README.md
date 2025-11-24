✅ equity01 残課題一覧 & 対応状況（2025/11/24 時点）
1. データ基盤（Raw / Processed）
項目	内容	状況
複数銘柄の parquet 化	27銘柄 → 94銘柄へ自動変換	✔ 完了（6th）
ユニバーススナップショット作成	月次 or 四半期ごとに保存	⏳ 未実装
東証休日カレンダー完全対応	祝日 / 臨時休場 / 標準カレンダーとの整合性	🔜 着手予定（EventGuard v0.3の前に必要）
Cutoff Policy（D-1 08:00 JST）	NY引け → 東京朝に確定させる処理	✔ 完了（6th）
NY祝日対応	FX/VIX/先物などの欠損処理	⏳ 未実装
2. Feature Builder（特徴量）
項目	内容	状況
ret_5 / 20 / vol_20 / ADV	基本特徴量	✔ 完了
出来高加速（volume acceleration）	ADV比の速度計算	⏳ 未実装
強度（strength）	ret_x 系の複合	⚠️ 廃止（不要と判断）
heat_flag（過熱抑制）	Zスコアベース	✔ 実装済（v1.1）
Quick-FA（EPS改定/ROIC など）	速報系ファンダメンタル	❌ 未実装（別フェーズ）
3. Scoring Engine（スコアリング）
項目	内容	状況
Z-score 正規化	ret/vol/adv を標準化	✔
Penalty（流動性 / 過熱 / vol）	特性ペナルティ	✔
σ補正（σ^β）	weight 配分の軸	✔
Large/Mid/Small の均等化	size bucket の正規化	✔（6th）
スコア保存（daily_feature_scores）	parquet化	✔
top N 選抜	スコア上位採用	✔
4. Portfolio Builder（ポートフォリオ生成）
項目	内容	状況
size bucket（Large/Mid/Small）分類	流動性分位による分類	✔
weight 正規化（等金額）	1/N方式（暫定）	✔
ポジション数制御（max names）	上位N銘柄採用	✔
decision_date / trading_date	cutoff反映	✔（7th）
β制御ロジック（ETFで階段制御）	現物×ETF で β ≈ 0.6/0.4/0.2	⏳ 未実装（後述）
レバレッジ管理（VAR ≤ 2%）	シミュレーション	❌ まだ未着手
5. EventGuard（イベント反射層）
バージョン	内容	状況
v0.1	skeleton & pass-through	✔ 完了
v0.2	flag_earnings / soft_guard / guard_factor	✔ 完了（7th）
v0.3	先物・為替・VIX の閾値判定	⏳ 未実装（次フェーズ）
v0.4	BOJ/FOMCスコアリング（LLM判定）	❌ 未着手
v1.0	Guard 層全体の統合（ALPHAERSへ）	🔜 2026Q1
6. レジーム判定（market regimes）
項目	内容	状況
equity01 内部の簡易レジーム	モメンタム×VIX	⚠️ 導入見送り
ALPHAERS（統合戦略）側に移管	戦略横断のレジーム	✔ 決定済（方針確定）
breadth PCA（市場広さ）	市場中立レジーム判定	⏳ 未実装
HMM 2/3-state	上昇・下降・ボラ	❌ 未着手
7. Intraweek Overlay（週内ロジック）
項目	内容	状況
月→木：通常	稼働	🔄 検討中
木→金：軽度縮小	金曜イベント回避	⏳ 未実装
金→月：ポジション禁止	週跨ぎリスク	⏳ 未実装
週内 β	0.5→0.35→0.2	❌ 未実装
8. ペーパートレード（単体テスト）
項目	内容	状況
forward return 計算	D→D+1 リターン	✔
daily_trade.csv 出力	パフォーマンス基盤	✔
Sharpe / DD / exposure 計算	QA基盤	✔
複数銘柄（94銘柄）化	✔（7th）	
勝因/敗因分析（explainability）	文章生成	⏳ 未実装（LLMで可能）
9. 品質保証（QA）
項目	内容	状況
なぜその投資判断か説明可能か	QA基準	✔ 策定済
市場環境と整合性があるか	外部要因照合	🔄 部分
非合理挙動の切り分け	スコア vs レジーム	🔄
スコア分布チェック	hist, QQ plot	✔
銘柄ごとの寄与度分析	戦略因果性	未実装
10. 外部接続（β・指数・ETF）
項目	内容	状況
index loader（TOPIX/日経225）	指数と連動	⏳
ETF loader（1570, 1306）	β制御のため	⏳
β計算	cov/var ベース	❌ 未実装
correlation matrix（11資産）	ALPHAERS側で利用	🔜
11. その他の残課題
項目	内容	状況
ログの最適化	print → logger 構造へ	⏳
エラー吸収（str/None/MultiIndex）	feature builderで改善済	✔
outlier 処理	price jump, zero volume	⏳
スコア保存世代管理	scores_YYYYMMDD.parquet	✔
バックテスト最適化（高速化）	vectorize / merge削減	🔜
🔎 残課題を優先度順に整理（A/B/C）
A：最優先（次フェーズで実装）

EventGuard v0.3（先物・為替・VIX）

β制御（ETF 階段ベース）

Intraweek Overlay（週内ロジック）

レジーム判定（ALPHAERS 側へ切り出し）

NY祝日対応＋cutoffの完全対応

B：次優先（単体テストの品質向上）

スコア分布・因果性 QA

勝因/敗因の自動説明（LLM）

ユニバーススナップショット（月次）

C：中期（2026Q1〜）

breadth PCA

HMM（2-3 state）

Multi-Horizon Ensemble

VAR/レバレッジ管理

🧩 まとめ：現状到達点

6th〜7th commit で、equity01 の “戦略単体として動く最低限の機能” が完成

特徴量 → スコア → PF → Guard → ペーパートレード の流れが 完全自動化

次は EventGuard / β制御 / Intraweek の3点セット が主力テーマ




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

