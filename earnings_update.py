"""Weekly earnings-estimates update -> data/earnings.csv
For every stock in tickers.csv it collects (from Yahoo Finance analyst data):
  next_earnings      date of the next report
  rev_est_bn         consensus revenue for the quarter being reported, in US$ billions
  rev_yoy            ... growth vs the same quarter last year
  eps_est            consensus EPS for that quarter (company reporting currency)
  eps_yoy            ... growth vs the same quarter last year
  eps_fy_px          consensus EPS for the current fiscal year, converted to the share-price currency
                     (the dashboard divides the live price by this to show the implied P/E)
Runs weekly (weekly_earnings.yml). Missing data stays blank - coverage is thinner for Asian stocks.
"""
import os, sys, time
from datetime import date
import pandas as pd
import yfinance as yf

os.makedirs("data", exist_ok=True)
meta = pd.read_csv("tickers.csv").drop_duplicates("ticker")
if "watchlist" not in meta: meta["watchlist"] = "sp500"
if "currency" not in meta: meta["currency"] = "USD"
today = date.today()

def num(x):
    try:
        x = float(x)
        return None if pd.isna(x) else x
    except (TypeError, ValueError):
        return None

_fx = {"USD": 1.0}
def rate(c):
    """units of currency c per 1 US$ (fetched on first use)"""
    if c not in _fx:
        try:
            _fx[c] = float(yf.download(f"{c}=X", period="5d", progress=False)["Close"].dropna().iloc[-1])
        except Exception as e:
            print("FX failed", c, repr(e)[:60])
            _fx[c] = None
    return _fx[c]

def row_of(df, key, col):
    try:
        return num(df.loc[key, col])
    except Exception:
        return None

def next_date(cal):
    d = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if d is None: return None
    ds = [x for x in (d if isinstance(d, (list, tuple)) else [d]) if x]
    ds = sorted(pd.to_datetime(x).date() for x in ds)
    fut = [x for x in ds if x >= today]
    return (fut[0] if fut else ds[0]).isoformat() if ds else None

def fetch(t, price_ccy):
    tk = yf.Ticker(t)
    r = {"ticker": t}
    try: cal = tk.calendar
    except Exception: cal = {}
    r["next_earnings"] = next_date(cal)
    try: ee = tk.earnings_estimate
    except Exception: ee = None
    try: re_ = tk.revenue_estimate
    except Exception: re_ = None
    fin = "USD"
    if price_ccy != "USD":  # reporting currency can differ from the share-price currency (e.g. HK-listed Chinese firms)
        try: fin = (tk.info or {}).get("financialCurrency") or price_ccy
        except Exception: fin = price_ccy
    rev = row_of(re_, "0q", "avg") if re_ is not None else None
    if rev is None and isinstance(cal, dict): rev = num(cal.get("Revenue Average"))
    eps = row_of(ee, "0q", "avg") if ee is not None else None
    if eps is None and isinstance(cal, dict): eps = num(cal.get("Earnings Average"))
    r.update({"_rev": rev, "rev_yoy": row_of(re_, "0q", "growth") if re_ is not None else None,
              "eps_est": eps, "eps_yoy": row_of(ee, "0q", "growth") if ee is not None else None,
              "_eps_fy": row_of(ee, "0y", "avg") if ee is not None else None,
              "_fin": fin,
              "analysts": row_of(ee, "0q", "numberOfAnalysts") if ee is not None else None})
    return r

if __name__ == "__main__":
    rows, failed = [], []
    for i, m in enumerate(meta.itertuples(), 1):
        try:
            r = fetch(m.ticker, m.currency)
            fin = r.pop("_fin"); rev = r.pop("_rev"); fy = r.pop("_eps_fy")
            r["fin_currency"] = fin
            rf, rp = rate(fin), rate(m.currency)
            r["rev_est_bn"] = round(rev / rf / 1e9, 3) if rev is not None and rf else None
            r["eps_fy_px"] = round(fy * rp / rf, 4) if fy is not None and rf and rp else None
            r["updated"] = today.isoformat()
            rows.append(r)
        except Exception as e:
            failed.append(m.ticker); print("failed", m.ticker, repr(e)[:80])
        if i % 50 == 0: print(f"{i}/{len(meta)}")
        time.sleep(0.4)
    df = pd.DataFrame(rows)
    have = df[["next_earnings", "rev_est_bn", "eps_est"]].notna().any(axis=1).sum() if len(df) else 0
    print(f"Stocks with some estimate data: {have} of {len(meta)}. Errors: {failed[:30]}")
    if have < len(meta) * 0.3:
        sys.exit("Too little data returned - keeping the previous earnings.csv.")
    cols = ["ticker", "next_earnings", "rev_est_bn", "rev_yoy", "eps_est", "eps_yoy",
            "eps_fy_px", "fin_currency", "analysts", "updated"]
    df[cols].to_csv("data/earnings.csv", index=False)
    print("OK: data/earnings.csv written")
