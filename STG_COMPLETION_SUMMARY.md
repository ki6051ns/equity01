# equity01 stg移行完了サマリ

**完了日**: 2025-12-20  
**バージョン**: v3.0（stg移行完了版）

---

## 🎯 stg移行の目標

**「再現可能な実行入口」を確保し、stg→prd移行の設計線を明確にする**

---

## ✅ 完了した作業

### stg①: ディレクトリ整理

- ✅ MVP最小構成（core 11本）を固定
- ✅ .gitignoreでvenv/生成物/研究物を隔離
- ✅ scripts/をcore/analysis/toolsに分割

### stg②: import整合性修正

- ✅ importエラーを解消（compute_scores_all, run_from_configを追加）
- ✅ core → analysis依存を削除
- ✅ 実行テスト成功（ImportErrorゼロ、パイプライン完走）

### stg③: 評価の統合と運用ドキュメント

- ✅ analysis/run_eval_report.pyを作成（統合評価の受け皿）
- ✅ README.mdを更新（セットアップ、実行方法、データ配置、フォールバック仕様）
- ✅ stgレビュー項目テンプレートを作成（四半期レビュー用）

---

## 📊 到達点

### 実行エントリポイント

```bash
# 基本実行（推奨）
python scripts/core/run_equity01_eval.py

# 統合評価レポート生成（オプション）
python scripts/analysis/run_eval_report.py
```

### 設計ルール（確定）

- ✅ `core → tools`: OK
- ❌ `core → analysis`: 禁止
- ✅ `analysis → core`: OK（coreの成果物を読み込む）
- ✅ `analysis → tools`: OK

### データ管理

- **Git管理**: `data/raw/`, `configs/`
- **Git管理外**: `data/processed/`, `data/intermediate/`, `research/reports/`, `venv/`

---

## 📁 ディレクトリ構造（最終形）

```
equity01/
├── README.md                    # 運用ドキュメント（stg/prd向け）
├── requirements.txt
├── config.py
├── .gitignore                   # venv/生成物/研究物を除外
│
├── scripts/
│   ├── core/                   # MVP最小構成（11ファイル）
│   │   └── run_equity01_eval.py  # 実行エントリポイント
│   ├── analysis/               # 研究・検証用（約35ファイル）
│   │   └── run_eval_report.py   # 統合評価レポート生成
│   └── tools/                  # 補助・ユーティリティ（約15ファイル）
│
├── data/
│   ├── raw/                    # 生データ（Git管理）
│   ├── processed/              # 生成物（.gitignore）
│   └── intermediate/           # 中間生成物（.gitignore）
│
├── research/
│   └── reports/                # 研究用レポート（.gitignore）
│
└── docs/
    ├── stg_review_template.md  # 四半期レビューテンプレート
    └── history/                # 進捗報告書アーカイブ（.gitignore）
```

---

## 🔄 TOPIXデータ取得のフォールバック仕様（確定）

### 仕様

1. **デフォルト**: `^TOPX` (yfinance) を試行
2. **フォールバック**: `^TOPX` が取得できない場合、自動的に `1306.T` (TOPIX連動ETF) を使用
3. **ログ出力**: フォールバック発生時は必ずログに記録（監査性確保）

### 実装場所

- `scripts/tools/build_index_tpx_daily.py`
- README.mdに仕様を記載

---

## 📋 次回レビューまでのチェック項目

四半期レビューでは `docs/stg_review_template.md` を使用：

1. データ取得成功率
2. STOP Regime発火率（想定: 11.8%付近）
3. ターンオーバー/売買回数
4. 主要な例外ログ（フォールバック回数含む）
5. システム動作確認（実行エントリポイント、import整合性）

---

## 🚀 prd移行への準備

stg移行により以下が整備されました：

1. **再現可能な実行入口**: 1本のコマンドで完結
2. **明確な設計ルール**: core → analysis依存ゼロ
3. **運用ドキュメント**: README.md、レビューテンプレート完備
4. **データ管理方針**: Git管理範囲が明確

**prd移行時は以下を実施**:
- analysis/の削除または別リポジトリへの分離
- core/のみをprdに持ち込む
- 実行エントリポイントはそのまま使用可能

---

**Prepared by**  
equity01 / Strategy Core Layer  
stg移行完了版 / Updated 2025-12-20

