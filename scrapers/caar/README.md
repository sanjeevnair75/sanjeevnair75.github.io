# CAAR Tracker

Auto-refreshing analytics dashboard for India's Customs Authority for Advance Rulings (CAAR), covering both Mumbai and Delhi benches, both Rulings and Orders.

## Architecture

```
GitHub Actions (Sundays 04:00 IST)
    |
    v
caar_unified_scraper.py  -- scrapes CBIC portal
    |
    v
postprocess.py           -- classifies issues, extracts year
    |
    v
build_dashboard.py       -- generates caar-tracker.html
build_excel.py           -- generates caar_analytics.xlsx
    |
    v
git commit & push        -- updates jurisnair.com
```

## Files

| File | Purpose |
|------|---------|
| `caar_unified_scraper.py` | Scrapes all 4 CAAR sections from cbic.gov.in |
| `postprocess.py` | Adds issue classification and year columns |
| `build_dashboard.py` | Generates `caar-tracker.html` (password-protected) |
| `build_excel.py` | Generates `caar_analytics.xlsx` (multi-sheet workbook) |
| `requirements.txt` | Python dependencies |

## Outputs (in `/data/caar/`)

| File | Description |
|------|-------------|
| `caar_all.csv` | All 953+ records consolidated |
| `caar_all.json` | Same as above, JSON format |
| `caar_all_enriched.csv` | With issue_type and year columns |
| `caar_all_enriched.json` | Same, JSON format |
| `caar_analytics.xlsx` | 6-sheet Excel workbook |
| `mumbai_rulings.csv` / `.json` | Per-section files |
| `mumbai_orders.csv` / `.json` | |
| `delhi_rulings.csv` / `.json` | |
| `delhi_orders.csv` / `.json` | |
| `snapshots/` | Historical snapshots, one per refresh |

## Dashboard

The live dashboard is at `caar-tracker.html` (root of the repository, served by GitHub Pages at `jurisnair.com/caar-tracker.html`). Password-protected with the same credentials as the BHC tracker.

## Manual Refresh

To trigger a refresh outside the weekly schedule:
1. Go to the GitHub repository
2. Click "Actions" tab
3. Select "CAAR Weekly Refresh" from the left sidebar
4. Click "Run workflow" -> "Run workflow" (green button)

The run takes about 5-7 minutes.

## Source

Data is scraped from the CBIC public portal:
- https://www.cbic.gov.in/entities/cbic-content-mst/NzU=
