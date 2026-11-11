"""Loads past daily closing prices into data/prices.csv (prices only, no percentages).
Usage:  python backfill_prices.py 30      -> last 30 trading days (default)
Safe to re-run: days already stored are kept, only missing days are added.
The daily job (update_data.py) then calculates 1D / 5D / 1M changes from these prices.
"""
import json, os, sys, time
import pandas as pd
import yfinance as yf

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
cfg = json.load(open("config.json"))
meta = pd.read_csv(cfg["tickers_file"]).drop_duplicates("ticker")
tickers = meta["ticker"].str.strip().tolist()
BATCH, RETRIES = 50, 3
os.makedirs("data", exist_ok=True)
# ask Yahoo for enough calendar days to cover the requested trading days
period = f"{int(DAYS * 1.6) + 10}d"

def download_batch(batch):
    for attempt in range(1, RETRIES + 1):
        try:
            df = yf.download(batch, period=period, auto_adjust=False, group_by="ticker",
                             threads=False, progress=False)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            print(f"  error (attempt {attempt}): {e!r}")
        time.sleep(5 * attempt)
    return None

if __name__ == "__main__":
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
                close = data["Close"].dropna().tail(DAYS)
                for d, p in close.items():
                    v = data["Volume"].get(d)
                    rows.append({"date": d.date().isoformat(), "ticker": t, "price": round(float(p), 4),
                                 "volume": int(v) if pd.notna(v) else None})
            except Exception:
                failed.append(t)
        time.sleep(2)
    print(f"Collected {len(rows)} price rows. Failed tickers: {failed[:30]}")
    got = {r["ticker"] for r in rows}
    wl = dict(zip(meta["ticker"], meta["watchlist"])) if "watchlist" in meta else {}
    for name in sorted(set(wl.values())) or [None]:
        want = [t for t in tickers if wl.get(t) == name] if name else tickers
        print(f"  {name}: {len([t for t in want if t in got])} of {len(want)} loaded")
        if len([t for t in want if t in got]) < len(want) * 0.8:
            sys.exit(f"Too few {name} tickers returned - nothing written.")
    new = pd.DataFrame(rows)
    try:
        old = pd.read_csv(cfg["output_prices"])
        prices = pd.concat([new, old]).drop_duplicates(["date", "ticker"], keep="last")
    except FileNotFoundError:
        prices = new
    prices.sort_values(["date", "ticker"]).to_csv(cfg["output_prices"], index=False)
    print(f"OK: prices.csv now covers {prices['date'].nunique()} days, {prices['date'].min()} to {prices['date'].max()}")
