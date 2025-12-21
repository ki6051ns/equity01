# Ladder仕様（ソース・オブ・トゥルース）

## 概要

ラダー方式（ladder）のバックテスト仕様を、コードから抽出した根拠行リンクで記録します。

---

## 仕様の要点

### ラダー方式の定義

**仕様:**
- 毎営業日で新しい「チケット」を発行し、それをh営業日保持するラダー方式
- 任意のhorizon hに対して、日次のターゲットウェイトは「直近h本のターゲットウェイトの平均」で構成する

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:101-119`](scripts/analysis/horizon_ensemble.py#L101-L119) - `backtest_with_horizon`関数の定義とdocstring

### リバランス日判定

**仕様:**
- **リバランス日判定は存在しない**（毎日新しいweightsを生成）
- **offset（ずらし）も存在しない**（毎日生成）

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:156`](scripts/analysis/horizon_ensemble.py#L156) - 全営業日をループ
- [`scripts/analysis/horizon_ensemble.py:173`](scripts/analysis/horizon_ensemble.py#L173) - 毎日`build_daily_portfolio`を呼び出し

### キューによる保持

**仕様:**
- 過去h本のclean weightsをキューに保持
- キューに最大horizon本まで保持し、超えたら古いものを`pop(0)`で削除

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:149-150`](scripts/analysis/horizon_ensemble.py#L149-L150) - キュー初期化
- [`scripts/analysis/horizon_ensemble.py:256-258`](scripts/analysis/horizon_ensemble.py#L256-L258) - キューに追加し、最大horizon本を超えたら削除

### 当日ウェイトの計算

**仕様:**
- キュー内の全ウェイトを平均（インデックスを揃える）
- 開始直後は`len(last_weights) < horizon`なので、その時点での平均を使用

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:260-278`](scripts/analysis/horizon_ensemble.py#L260-L278) - キュー内の全ウェイトを平均化

### 60/90/120の束ね方

**仕様:**
- 60/90/120はそれぞれ独立したhorizonとして扱う（3本ラダー等の特別な束ね方はない）
- それぞれのhorizonで独立してラダー方式を実行

**根拠行:**
- [`scripts/analysis/ensemble_variant_cross4.py:38-45`](scripts/analysis/ensemble_variant_cross4.py#L38-L45) - WEIGHTS定義（各horizonが独立）

### 売買単位（持ち越し/当日更新）

**仕様:**
- 毎日新しいweightsを生成（当日更新）
- キュー内の過去h本の平均を使用するため、実質的に「持ち越し」の効果がある

**根拠行:**
- [`scripts/analysis/horizon_ensemble.py:173`](scripts/analysis/horizon_ensemble.py#L173) - 毎日`build_daily_portfolio`を呼び出し
- [`scripts/analysis/horizon_ensemble.py:278`](scripts/analysis/horizon_ensemble.py#L278) - キュー内の平均を計算

---

## weights生成への移植方針

### nonladder

- **horizon間隔でリバランスし、そのweightsをhorizon日ホールド（複製）**
- 例: horizon=5の場合、0, 5, 10, 15日目にリバランスし、それぞれのweightsを5日間ホールド

### ladder（60/90/120）

1. **毎日weightsを生成**（`build_daily_portfolio`を呼び出し）
2. **キューに保持**（最大horizon本まで）
3. **当日weightsはキュー内の平均**（過去h本の平均）
4. **全営業日のweightsを生成**（データがない日でも、キューがあれば前回weightsを維持）

**重要:**
- ラダー方式は「毎日新しいweightsを生成してキューに追加し、過去h本の平均を使用」する方式
- 全営業日のweightsを生成するため、データがない日でもキューから前回weightsを計算して出力

---

## 参照

- `scripts/analysis/horizon_ensemble.py` - ラダー方式の実装
- `scripts/analysis/backtest_non_ladder.py` - 非ラダー方式の実装（参考）

