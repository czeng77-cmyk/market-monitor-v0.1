"""Daily S&P 500 data update.
1) Downloads prices from Yahoo Finance (small batches, retries).
2) Stores daily closing prices in data/prices.csv (one row per stock per day).
   The most recent days are re-saved each run, so any missed day fills itself in.
3) Calculates 1D, 5D and 1M changes from the STORED prices. 3M and YTD use the
   1-year Yahoo download. If stored history is too short for 5D/1M, the Yahoo
   figure is used instead until enough history has built up.
Output: data/latest.csv (today's snapshot) and data/prices.csv (price history).
Settings live in config.json.
"""
import json, os, sys, time
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

cfg = json.load(open("config.json"))
meta = pd.read_csv(cfg["tickers_file"]).drop_duplicates("ticker")
tickers = meta["ticker"].str.strip().tolist()
BATCH, RETRIES = 50, 3
RECENT = cfg.get("refresh_recent_days", 10)
os.makedirs("data", exist_ok=True)

def download_batch(batch):
    for attempt in range(1, RETRIES + 1):
        try:
            df = yf.download(batch, period="1y", auto_adjust=False, group_by="ticker",
                             threads=False, progress=False)
            if df is not None and not df.empty:
                return df
            print(f"  empty result (attempt {attempt})")
        except Exception as e:
            print(f"  error (attempt {attempt}): {e!r}")
        time.sleep(5 * attempt)
    return None

def pct(now, then):
    return None if then is None or pd.isna(then) or then == 0 or pd.isna(now) else float(now / then - 1)

def base_before(close, cutoff):
    s = close[close.index <= cutoff]
    return s.iloc[-1] if len(s) else None

year_start = pd.Timestamp(datetime.now().year, 1, 1)
price_rows, yahoo, failed = [], {}, []
for i in range(0, len(tickers), BATCH):
    batch = tickers[i:i + BATCH]
    print(f"Batch {i // BATCH + 1}: {batch[0]}..{batch[-1]}")
    raw = download_batch(batch)
    if raw is None:
        failed += batch
        continue
    for t in batch:
        try:
            data = raw[t] if len(batch) > 1 else raw
            close = data["Close"].dropna()
            if len(close) < 2:
                raise ValueError("not enough price data")
            vol = data["Volume"]
            for d, p in close.tail(RECENT).items():
                v = vol.get(d)
                price_rows.append({"date": d.date().isoformat(), "ticker": t, "price": round(float(p), 4),
                                   "volume": int(v) if pd.notna(v) else None})
            last = close.index[-1]
            ytd_base = close[close.index < year_start]
            yahoo[t] = {  # fallbacks / 3M / YTD
                "chg_5d": pct(close.iloc[-1], close.iloc[-6]) if len(close) >= 6 else None,
                "chg_1m": pct(close.iloc[-1], base_before(close, last - pd.DateOffset(months=1))),
                "chg_3m": pct(close.iloc[-1], base_before(close, last - pd.DateOffset(months=3))),
                "chg_ytd": pct(close.iloc[-1], ytd_base.iloc[-1]) if len(ytd_base) else None,
            }
        except Exception:
            failed.append(t)
    time.sleep(2)

print(f"Got {len(yahoo)} of {len(tickers)} tickers. Failed: {failed[:30]}")
if len(yahoo) < len(tickers) * 0.8:
    sys.exit("Too few tickers returned - stopping so existing data isn't overwritten.")

# ---- 1) update stored prices
new = pd.DataFrame(price_rows)
try:
    prices = pd.concat([pd.read_csv(cfg["output_prices"]), new]).drop_duplicates(["date", "ticker"], keep="last")
except FileNotFoundError:
    prices = new
cutoff = (pd.Timestamp.now() - pd.Timedelta(days=cfg["history_keep_days"])).date().isoformat()
prices = prices[prices["date"] >= cutoff].sort_values(["date", "ticker"])
prices.to_csv(cfg["output_prices"], index=False)

# ---- 2) calculate changes from stored prices
rows = []
for t, g in prices.groupby("ticker"):
    if t not in yahoo:
        continue
    s = g.set_index(pd.to_datetime(g["date"]))["price"]
    last_date, price = s.index[-1], s.iloc[-1]
    if last_date != pd.Timestamp(prices["date"].max()):
        continue  # stale ticker (no price for the latest day)
    one_month_cutoff = last_date - pd.DateOffset(months=1)
    has_1m = s.index[0] <= one_month_cutoff
    y = yahoo[t]
    rows.append({
        "date": last_date.date().isoformat(), "ticker": t, "price": round(float(price), 4),
        "chg_1d": pct(price, s.iloc[-2]) if len(s) >= 2 else None,
        "chg_5d": pct(price, s.iloc[-6]) if len(s) >= 6 else y["chg_5d"],
        "chg_1m": pct(price, base_before(s, one_month_cutoff)) if has_1m else y["chg_1m"],
        "chg_3m": y["chg_3m"], "chg_ytd": y["chg_ytd"],
        "volume": g["volume"].iloc[-1],
    })

df = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
df["is_big_move"] = df["chg_1d"].abs() >= cfg["big_move_threshold"]
df["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
cols = ["date", "ticker", "company", "sector", "industry", "market_cap_bn", "price",
        "chg_1d", "chg_5d", "chg_1m", "chg_3m", "chg_ytd", "volume", "is_big_move", "updated_utc"]
df[cols].to_csv(cfg["output_latest"], index=False)
print(f"OK: {len(df)} stocks, data date {df['date'].max()}, {prices['date'].nunique()} days of prices stored")
