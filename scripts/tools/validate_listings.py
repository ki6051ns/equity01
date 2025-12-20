import sys, pandas as pd, re
from pathlib import Path

RE_TICK = re.compile(r"^\d{4}\.T$")  # 例: 7203.T

REQUIRED = ["ticker","market","type","name","sector"]

MARKETS = {"Prime","Standard","Growth"}

EXCLUDE_TYPES = {"ETF","REIT","Preferred","Warrant"}

def main(path):
    p = Path(path)
    df = pd.read_csv(p)

    # 列チェック
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        raise SystemExit(f"Missing columns: {miss}")

    # 正規化
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    # 4桁のみなら .T を付与
    df.loc[df["ticker"].str.fullmatch(r"\d{4}"), "ticker"] = df["ticker"] + ".T"

    # 形式チェック
    bad = df[~df["ticker"].str.fullmatch(RE_TICK)]
    if not bad.empty:
        print("WARN: Bad ticker rows -> will drop")
        print(bad[["ticker","name"]].head())
        df = df[df["ticker"].str.fullmatch(RE_TICK)]

    # マーケット正規化
    df["market"] = df["market"].str.strip().str.title()
    df = df[df["market"].isin(MARKETS)]

    # 重複除去
    df = df.drop_duplicates(subset=["ticker"], keep="first")

    # 余計な空白除去
    for c in ["type","name","sector"]:
        df[c] = df[c].astype(str).str.strip()

    # 保存（同名上書き）
    df.to_csv(p, index=False, encoding="utf-8")
    print(f"OK: {len(df)} rows valid -> {p}")

if __name__ == "__main__":
    if len(sys.argv)<2:
        print("Usage: python scripts/validate_listings.py data/raw/jpx_listings/20250930.csv")
        sys.exit(1)
    main(sys.argv[1])






