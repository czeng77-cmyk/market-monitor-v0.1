"""Collects recent headlines for the 10 biggest gainers and 10 biggest losers (1 day)
and writes data/news.json for the dashboard's Newsflow tab.
Runs after update_data.py. If it fails, the rest of the dashboard still works.
Add or change keyword rules in TAGS below.
"""
import json, re, time
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf

TOP_N, MAX_HEADLINES, MAX_AGE_DAYS = 10, 4, 4

TAGS = {  # tag -> keywords (lowercase)
    "Earnings": ["earnings", "quarterly results", "eps", "revenue", "profit", "q1", "q2", "q3", "q4", "beats", "misses"],
    "Guidance": ["guidance", "outlook", "forecast", "raises", "cuts", "lowers"],
    "Analyst call": ["upgrade", "downgrade", "price target", "initiates", "rating", "analyst", "overweight", "underweight"],
    "M&A / deals": ["acquire", "acquisition", "merger", "buyout", "takeover", "to buy", "deal", "stake"],
    "AI / semis": ["ai ", " ai", "artificial intelligence", "chip", "semiconductor", "data center", "gpu", "nvidia", "openai"],
    "Product / contract": ["launch", "unveil", "contract", "partnership", "approval", "fda", "order", "wins"],
    "Legal / regulatory": ["lawsuit", "probe", "investigation", "sec ", "antitrust", "tariff", "ban", "fine", "recall"],
    "Management": ["ceo", "cfo", "resign", "steps down", "appoint"],
    "Capital return": ["dividend", "buyback", "repurchase", "split"],
    "Macro / market": ["fed", "rate cut", "inflation", "jobs report", "treasury", "stocks rally", "stocks fall", "wall street"],
}

def parse_item(it):
    """Handles both Yahoo news formats."""
    c = it.get("content") or it
    title = c.get("title") or it.get("title")
    if not title:
        return None
    url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
           or it.get("link") or c.get("link") or "")
    pub = (c.get("provider") or {}).get("displayName") or it.get("publisher") or ""
    when = None
    if c.get("pubDate"):
        when = pd.to_datetime(c["pubDate"], utc=True, errors="coerce")
    elif it.get("providerPublishTime"):
        when = pd.to_datetime(it["providerPublishTime"], unit="s", utc=True, errors="coerce")
    return {"title": title.strip(), "publisher": pub, "url": url, "when": when}

def tag_headlines(titles):
    text = " ".join(titles).lower()
    return [tag for tag, kws in TAGS.items()
            if any(re.search(r"\b" + re.escape(k.strip()) + r"\b", text) for k in kws)][:4]

def get_news(ticker):
    for attempt in range(3):
        try:
            raw = yf.Ticker(ticker).news or []
            break
        except Exception as e:
            print(f"  {ticker}: error {e!r}")
            raw = []
            time.sleep(3)
    cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=MAX_AGE_DAYS)
    items = [p for p in (parse_item(r) for r in raw) if p]
    items = [p for p in items if p["when"] is None or pd.isna(p["when"]) or p["when"] >= cutoff]
    items.sort(key=lambda p: p["when"] if p["when"] is not None and not pd.isna(p["when"]) else cutoff, reverse=True)
    out = []
    for p in items[:MAX_HEADLINES]:
        w = p["when"]
        out.append({"title": p["title"], "publisher": p["publisher"], "url": p["url"],
                    "time": w.strftime("%Y-%m-%d %H:%M") + " UTC" if w is not None and not pd.isna(w) else ""})
    return out

def next_earnings(ticker):
    try:
        cal = yf.Ticker(ticker).calendar
        d = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if d:
            d = d[0] if isinstance(d, (list, tuple)) else d
            return str(d)[:10]
    except Exception:
        pass
    return None

if __name__ == "__main__":
    latest = pd.read_csv("data/latest.csv").dropna(subset=["chg_1d"])
    if "watchlist" not in latest:
        latest["watchlist"] = "sp500"
    picks = []
    for wl, grp in latest.groupby("watchlist"):  # top/bottom 10 within each watchlist
        ranked = grp.sort_values("chg_1d", ascending=False)
        picks += [(r, "gainer") for _, r in ranked.head(TOP_N).iterrows()]
        picks += [(r, "loser") for _, r in ranked.tail(TOP_N).iloc[::-1].iterrows()]
    items = []
    for r, side in picks:
        t = r["ticker"]
        print("News:", t)
        heads = get_news(t)
        items.append({"ticker": t, "company": r["company"], "sector": r["sector"], "side": side, "watchlist": r.get("watchlist", "sp500"),
                      "chg_1d": float(r["chg_1d"]), "price": float(r["price"]),
                      "tags": tag_headlines([h["title"] for h in heads]), "headlines": heads,
                      "earnings": next_earnings(t)})
        time.sleep(0.5)
    json.dump({"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
               "data_date": str(latest["date"].max()), "items": items},
              open("data/news.json", "w"), indent=1)
    print(f"OK: news for {len(items)} stocks")
