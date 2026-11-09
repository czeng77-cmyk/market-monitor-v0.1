"""Daily S&P 500 data update.
Reads tickers.csv, downloads prices from Yahoo Finance (yfinance), and writes:
  data/latest.csv   - one row per stock, newest values (overwritten daily)
  data/history.csv  - one row per stock per day (appended daily, for trends)
Settings live in config.json. To add a stock, add a row to tickers.csv.
"""
import json, sys
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

cfg = json.load(open("config.json"))
meta = pd.read_csv(cfg["tickers_file"]).drop_duplicates("ticker")
tickers = meta["ticker"].str.strip().tolist()

# Pull ~1 year so YTD and 3M can be calculated. Add Jan-1 buffer.
raw = yf.download(tickers, period="1y", auto_adjust=True, group_by="ticker",
                  threads=True, progress=False)

def pct(now, then):
    return None if then in (None, 0) or pd.isna(then) or pd.isna(now) else now / then - 1

year_start = pd.Timestamp(datetime.now().year, 1, 1)
rows = []
for t in tickers:
    try:
        close = raw[t]["Close"].dropna()
    except KeyError:
        continue
    if len(close) < 2:
        continue
    last_date, price = close.index[-1], close.iloc[-1]
    prev = close.iloc[-2]
    three_m = close[close.index <= last_date - pd.DateOffset(months=3)]
    ytd_base = close[close.index < year_start]
    rows.append({
        "date": last_date.date().isoformat(), "ticker": t,
        "price": round(float(price), 4),
        "chg_1d": pct(price, prev),
        "chg_3m": pct(price, three_m.iloc[-1]) if len(three_m) else None,
        "chg_ytd": pct(price, ytd_base.iloc[-1]) if len(ytd_base) else None,
        "volume": int(raw[t]["Volume"].dropna().iloc[-1]) if "Volume" in raw[t] else None,
    })

if len(rows) < len(tickers) * 0.8:
    sys.exit(f"Only {len(rows)}/{len(tickers)} tickers returned - aborting so good data isn't overwritten.")

df = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
df["is_big_move"] = df["chg_1d"].abs() >= cfg["big_move_threshold"]
df["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
cols = ["date","ticker","company","sector","industry","market_cap_bn","price","chg_1d","chg_3m",
        "chg_ytd","volume","is_big_move","updated_utc"]
df = df[cols]
df.to_csv(cfg["output_latest"], index=False)

# Append to history (skips days already stored, so reruns are safe)
try:
    hist = pd.read_csv(cfg["output_history"])
    hist = pd.concat([hist, df]).drop_duplicates(["date", "ticker"], keep="last")
except FileNotFoundError:
    hist = df
cutoff = (pd.Timestamp.now() - pd.Timedelta(days=cfg["history_keep_days"])).date().isoformat()
hist[hist["date"] >= cutoff].sort_values(["date","ticker"]).to_csv(cfg["output_history"], index=False)
print(f"OK: {len(df)} stocks, data date {df['date'].max()}")
