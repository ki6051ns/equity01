import pandas as pd

df = pd.read_parquet("data/intermediate/universe/latest_universe.parquet")
print(len(df), "names")
print(df.head(10)[["ticker", "avg_turnover", "liquidity_rank"]])




