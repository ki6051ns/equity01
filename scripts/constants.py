#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
scripts/constants.py

equity01プロジェクト全体で使用する共通定数

重要: このファイルは全スクリプトから参照されるため、
定数の変更は慎重に行い、変更時は全スクリプトの互換性を確認すること。
"""

# インバースETF ticker（Plan Aで使用）
INVERSE_ETF_TICKER = "1569.T"  # インバースTOPIX連動ETF

# TOPIXインデックスデータのパス
INDEX_TPX_PATH = "data/processed/index_tpx_daily.parquet"

# インバースETF価格データのパス（eval_stop_regimes.py準拠）
INVERSE_ETF_PRICE_PATHS = [
    "data/processed/inverse_returns.parquet",
    "data/processed/daily_returns_inverse.parquet",
    "data/raw/equities/1569.T.parquet",
]

