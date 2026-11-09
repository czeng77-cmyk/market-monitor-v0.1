"""Re-applies GICS sectors to tickers.csv.
Rule: a stock's sector = sector_overrides.csv if listed there, otherwise sector_map.csv (by its 'industry').
Run after adding stocks:  python map_sectors.py   (new stocks need an 'industry' or an override row)
"""
import pandas as pd
t = pd.read_csv("tickers.csv")
m = dict(pd.read_csv("sector_map.csv").values)
o = dict(pd.read_csv("sector_overrides.csv").values)
t["sector"] = [o.get(k, m.get(i, s)) for k, i, s in zip(t.ticker, t.industry, t.sector)]
t.to_csv("tickers.csv", index=False)
print(t.sector.value_counts())
