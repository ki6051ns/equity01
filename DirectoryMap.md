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
