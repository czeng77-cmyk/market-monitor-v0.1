"""Daily S&P 500 data update.
Reads tickers.csv, downloads prices from Yahoo Finance in small batches with retries,
and writes data/latest.csv (today's snapshot) and data/history.csv (appended daily).
Changes calculated: 1D, 5D, 1M, 3M and year-to-date. Settings live in config.json.
"""
import json, os, sys, time
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

cfg = json.load(open("config.json"))
meta = pd.read_csv(cfg["tickers_file"]).drop_duplicates("ticker")
tickers = meta["ticker"].str.strip().tolist()
BATCH, RETRIES = 50, 3
os.makedirs("data", exist_ok=True)

def download_batch(batch):
    for attempt in range(1, RETRIES + 1):
        try:
            df = yf.download(batch, period="1y", auto_adjust=True, group_by="ticker",
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
rows, failed = [], []
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
            last_date, price = close.index[-1], close.iloc[-1]
            ytd_base = close[close.index < year_start]
            vol = data["Volume"].dropna()
            rows.append({
                "date": last_date.date().isoformat(), "ticker": t,
                "price": round(float(price), 4),
                "chg_1d": pct(price, close.iloc[-2]),
                "chg_5d": pct(price, close.iloc[-6]) if len(close) >= 6 else None,
                "chg_1m": pct(price, base_before(close, last_date - pd.DateOffset(months=1))),
                "chg_3m": pct(price, base_before(close, last_date - pd.DateOffset(months=3))),
                "chg_ytd": pct(price, ytd_base.iloc[-1]) if len(ytd_base) else None,
                "volume": int(vol.iloc[-1]) if len(vol) else None,
            })
        except Exception:
            failed.append(t)
    time.sleep(2)

print(f"Got {len(rows)} of {len(tickers)} tickers. Failed: {failed[:30]}")
if len(rows) < len(tickers) * 0.8:
    sys.exit("Too few tickers returned - stopping so existing data isn't overwritten.")

df = pd.DataFrame(rows).merge(meta, on="ticker", how="left")
df["is_big_move"] = df["chg_1d"].abs() >= cfg["big_move_threshold"]
df["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
cols = ["date", "ticker", "company", "sector", "industry", "market_cap_bn", "price",
        "chg_1d", "chg_5d", "chg_1m", "chg_3m", "chg_ytd", "volume", "is_big_move", "updated_utc"]
df = df[cols]
df.to_csv(cfg["output_latest"], index=False)

try:
    hist = pd.read_csv(cfg["output_history"])
    hist = pd.concat([hist, df]).drop_duplicates(["date", "ticker"], keep="last")
except FileNotFoundError:
    hist = df
cutoff = (pd.Timestamp.now() - pd.Timedelta(days=cfg["history_keep_days"])).date().isoformat()
hist[hist["date"] >= cutoff].sort_values(["date", "ticker"]).to_csv(cfg["output_history"], index=False)
print(f"OK: {len(df)} stocks, data date {df['date'].max()}")
