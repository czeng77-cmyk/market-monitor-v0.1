"""Fetches market caps (converted to US$ billions) for stocks with no market cap in tickers.csv
(the Asia watchlist) and writes data/market_caps.csv. update_data.py uses it for the heatmap sizes.
Runs in the daily workflow; if it fails the dashboard falls back to equal-size tiles.
"""
import os, time
import pandas as pd
import yfinance as yf

os.makedirs("data", exist_ok=True)
meta = pd.read_csv("tickers.csv")
todo = meta[meta["market_cap_bn"].isna()]
fx = {}
for ccy in sorted(todo["currency"].dropna().unique()):
    if ccy == "USD":
        fx[ccy] = 1.0
        continue
    try:
        fx[ccy] = float(yf.download(f"{ccy}=X", period="5d", progress=False)["Close"].dropna().iloc[-1])  # units per US$
    except Exception as e:
        print("FX failed", ccy, e)
rows = []
for _, r in todo.iterrows():
    try:
        cap = yf.Ticker(r["ticker"]).fast_info["market_cap"]
        rate = fx.get(r["currency"])
        if cap and rate:
            rows.append({"ticker": r["ticker"], "market_cap_bn": round(float(cap) / rate / 1e9, 2)})
    except Exception as e:
        print("cap failed", r["ticker"], repr(e)[:80])
    time.sleep(0.3)
if len(rows) >= len(todo) * 0.5:
    pd.DataFrame(rows).to_csv("data/market_caps.csv", index=False)
print(f"OK: market caps for {len(rows)} of {len(todo)} stocks")
