# S&P 500 Daily Dashboard – Setup Guide (Power BI)

How it fits together:
GitHub Action (daily) -> runs update_data.py -> writes data/latest.csv + data/history.csv -> Power BI reads those files -> dashboard.

## What's in this folder
| File | Purpose |
|---|---|
| tickers.csv | Your stock list (ticker, company, GICS sector, original industry, market cap) taken from your Excel file. **Add/remove stocks here.** |
| sector_map.csv / sector_overrides.csv / map_sectors.py | Industry-to-GICS mapping, per-stock exceptions, and the script that applies them. |
| config.json | Settings: "big move" threshold (default 5%), history length, file names. |
| update_data.py | Downloads prices and calculates 1D / 3M / YTD changes. |
| requirements.txt | Libraries the script needs. |
| .github/workflows/daily_update.yml | The daily schedule (Mon-Fri, 05:30 Beijing time). |

## Part 1 – Put the automation online (about 15 min)
1. Create a free account at github.com.
2. Click **New repository**. Name it `sp500-monitor`, choose **Public**, tick "Add a README", click Create.
   (Public is needed so Power BI can read the data without sign-in. It only contains public market data.)
3. Click **Add file > Upload files**. Drag in everything from this folder, **including the hidden `.github` folder** and an empty `data` folder (GitHub ignores empty folders; the first run creates it). Click Commit.
   Tip: if the `.github` folder won't upload by drag-and-drop, use Add file > Create new file, type `.github/workflows/daily_update.yml` as the name, and paste the file's contents.
4. Go to **Actions** tab > "Daily stock update" > **Run workflow**. Wait ~2–4 minutes for a green tick.
5. Open the `data` folder in the repo. You should see `latest.csv` and `history.csv`. If the run failed, click it to read the error and send it to me.
6. From now on it runs automatically every weekday. Weekends and holidays simply re-use the last trading day (no duplicates are created).

## Part 2 – Build the dashboard in Power BI Desktop (free, Windows)
Download Power BI Desktop from the Microsoft Store.
1. **Get data > Web.** Paste (replace YOUR-NAME):
   `https://raw.githubusercontent.com/YOUR-NAME/sp500-monitor/main/data/latest.csv`
   Click OK > Anonymous > Connect > **Transform Data**. Check the first row is the header (Use First Row as Headers) and column types: percentages = Decimal Number, `date` = Date. Close & Apply.
2. Repeat step 1 with `.../data/history.csv` (name this table **History** and the first one **Latest**).
3. Format the % columns: select a column > Column tools > Format > Percentage, 2 decimals.
4. Add these measures (Modeling > New measure) so the report is easy to extend:
   - `Avg 1D = AVERAGE(Latest[chg_1d])`
   - `Advancers = COUNTROWS(FILTER(Latest, Latest[chg_1d] > 0))`
   - `Decliners = COUNTROWS(FILTER(Latest, Latest[chg_1d] < 0))`
   - `Big Movers = COUNTROWS(FILTER(Latest, Latest[is_big_move] = TRUE()))`
5. **Page 1 – Daily Overview**, build these visuals:
   - Cards: Data date (max of `date`), Avg 1D, Advancers, Decliners, Big Movers.
   - **Top 10 gainers**: Table (ticker, company, chg_1d, price). Filters pane > ticker > Filter type **Top N** > Top 10 by `chg_1d`.
   - **Top 10 losers**: same, choose **Bottom 10**.
   - **Sector heatmap**: Treemap. Group = sector, Values = market_cap_bn (Sum). Format > Colors > fx rule on Avg 1D (red-white-green, centre 0).
   - **Sector performance**: Clustered bar, Axis = sector, Values = Avg of chg_1d / chg_3m / chg_ytd.
   - **Slicer**: sector.
6. **Page 2 – Trends**: Line chart from History: Axis = date, Values = Average of chg_1d, Legend = sector (this grows more useful each day). Add a slicer on ticker, plus a line chart of price for the chosen stock.
7. **Page 3 – Detail table**: all stocks, sortable, with conditional-format colours on the % columns.
8. Save as `SP500_Dashboard.pbix`.

## Part 3 – Publish and auto-refresh
1. In Power BI Desktop click **Publish** and sign in with your Microsoft account (free work/school or personal-with-trial accounts vary; a Power BI Pro/Fabric trial may be needed for scheduled refresh).
2. In app.powerbi.com open the dataset > **Settings > Data source credentials**: authentication = Anonymous, privacy = Public.
3. **Scheduled refresh**: On, daily, set a time **after 06:30 Beijing time** (the Action finishes ~05:45).
4. Pin to a dashboard or use the mobile app to view daily.
Without Pro: you can still open the .pbix and click **Refresh** daily.

## Making changes later
| I want to… | Do this |
|---|---|
| Add/remove a stock | Edit `tickers.csv` on GitHub (pencil icon). |
| Change what counts as a big move | Edit `big_move_threshold` in `config.json` (0.05 = 5%). |
| Keep history longer/shorter | Edit `history_keep_days`. |
| Add a new metric (e.g. 1-week change, volume spike, 52-week high) | Add a column in `update_data.py` rows block + the `cols` list; in Power BI click Refresh and the new column appears. |
| Change the run time | Edit the `cron` line in the workflow (times are UTC). |
| Add other markets/ETFs/indices | Add their Yahoo tickers (e.g. `^GSPC`, `SPY`, `0700.HK`) to `tickers.csv`. |

## Known limits
- Data comes from Yahoo Finance via the free `yfinance` library (unofficial; occasional hiccups). The script refuses to overwrite good data if fewer than 80% of tickers return.
- Market cap and sector in `tickers.csv` are a snapshot from your workbook; refresh occasionally (quarterly is fine). Forward P/E from your Excel file isn't included because Yahoo's bulk download doesn't provide it; it can be added as a later enhancement.
- `sector` is now one of the 11 GICS sectors. Your original Excel category is kept in the `industry` column, so you can still drill down. Mapping is by industry (`sector_map.csv`) with per-stock exceptions in `sector_overrides.csv`; edit those, then run `python map_sectors.py`. It is a close approximation of official GICS, not a licensed data feed.
