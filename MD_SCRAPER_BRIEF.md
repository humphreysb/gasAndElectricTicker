# Task brief: Add a Maryland scraper to RateSavvy

This is the same shape as the PA brief that worked. Read `PA_SCRAPER_BRIEF.md` history (`git log -p MARKET_EXPANSION.md`) or scan `scrapers/pa.py` and the PA-related entries in `providers.py` and `build_dashboard.py` for the working template.

## What "done" looks like

- `scrapers/md.py` exists, exposes `STATE = 'MD'` and a callable `scrape()` returning today's combined electric + gas rows with the standard column shape.
- `providers.STATES['MD']` lists Maryland's electric EDCs and gas LDCs with their site IDs as keys.
- `scrapers/__init__.py` registers the module (`ALL_SCRAPERS = [oh, pa, md]`).
- `build_dashboard.py` `STATE_CONFIG` has a `'MD'` entry with `name='Maryland'`, `elec_file='md-electric_dashboard.html'`, `gas_file='md-gas_dashboard.html'`, and threshold rates tuned to MD's residential supply prices (electric ~$0.09/kWh, gas ~$1.00/therm or ~$10/Mcf — confirm against the live site).
- Running `python energy_scraper.py` then `python build_dashboard.py` produces `md-electric_dashboard.html` and `md-gas_dashboard.html` alongside the existing files.
- All 14 unittests pass (`python -m unittest discover tests`).

## Read these first

1. `ARCHITECTURE.md` — section 5 lists this state and the pattern.
2. `scrapers/pa.py` — your closest template. Same dual-fuel structure.
3. `scrapers/oh.py` — the original. Different table format but same column shape.
4. `providers.py` — see how PA and OH are registered. Pick the same key style (integer IDs if MD uses them, string codes if it doesn't).
5. `build_dashboard.py` — search `STATE_CONFIG`. Single new entry needed.

## The MD sites

- **Electric:** https://www.marylandelectricchoice.com — run by the MD Public Service Commission
- **Gas:** https://www.mdgaschoice.com — same

### Residential delivery utilities to cover

**Electric (EDCs):**
- BGE (Baltimore Gas & Electric)
- Pepco
- Delmarva Power
- Potomac Edison (FirstEnergy)
- Choptank Electric Cooperative — *small co-op, may not be in the marketplace. Skip if absent.*
- SMECO (Southern Maryland Electric Cooperative) — *co-op, same caveat.*

**Gas (LDCs):**
- BGE Gas
- Washington Gas Light
- Columbia Gas of Maryland
- Elkton Gas — *small. Skip if absent.*

Focus on the four big EDCs and three big LDCs. Co-ops can be left as `# TODO` if they're not surfaced in the comparison engine.

## Required column shape (same as PA / OH)

| Column | Type | Notes |
|---|---|---|
| `Supplier` | str | Clean: split on `(` and take the first part |
| `Rate Type` | str | Source string |
| `Renew. Content` | float | Percent renewable, 0–100, numeric |
| `intro. price` | bool | |
| `Term. Length` | float | Months. Strip non-digits if formatted as "12 mo" |
| `Early Term. Fee` | float | Dollars |
| `Monthly Fee` | float | Dollars |
| `promo. offers` | bool | |
| `electric` | bool | True for electric, False for gas |
| `rate` | float | Electric: $/kWh. Gas: $/Mcf. **MD gas sites often report $/therm — convert to $/Mcf by multiplying by 10.32** (1 Mcf ≈ 10.32 therms, standard EIA assumption). |
| `Fixed Rate` | bool | True if `Rate Type` contains "Fixed" |
| `Todays Data` | bool | Always True on freshly scraped rows |
| `Date` | datetime | `datetime.now(pytz.timezone('US/Eastern'))` |
| `Provider` | int or str | Whatever MD's site uses as the EDC/LDC identifier. Mirror in `providers.STATES['MD']`. |

**Do NOT add a `state` column.** The dispatcher adds it.

## Investigation steps before coding

1. `curl -s "https://www.marylandelectricchoice.com/..." | grep -i '<table'` — does the rate page return server-rendered HTML, or is it client-side JS?
2. Find the URL pattern that filters to one EDC. ZIP code? EDC ID query param? Form POST?
3. Confirm the comparison table has the columns we need (term, rate, fee, ETF, intro/promo flags, fixed/variable). If a column is missing, decide whether to derive it (e.g., `Fixed Rate` from `Rate Type`) or leave it None.
4. Repeat for `mdgaschoice.com`.

**If the data is only reachable via a headless browser, stop and report back.** We're not adding Selenium/Playwright — that breaks the free-tier discipline rules in `ARCHITECTURE.md`.

## Constraints

- Use only `requests`, `pandas`, `pytz`, `urllib3`. No new top-level deps.
- Add `time.sleep(1)` between utility requests to avoid hammering MD PSC's site.
- Don't edit `build_dashboard.py` beyond the single `STATE_CONFIG` entry. If you need to, stop and ask.
- Don't change `allData.parquet`'s column shape. MD rows append to the existing schema.
- Skip exotic small utilities with `# TODO` rather than wedge them in.

## Out of scope

- README updates
- MARKET_EXPANSION.md updates
- CHANGELOG.md updates
- Pushing the branch or opening a PR
- Any Cloudflare R2 / Workers / Pages work — that's a separate migration
- Backfill of historical MD data — that's a follow-up after the live scraper is verified

## Report back with

- The exact URL patterns used (so we can audit and re-run manually).
- Utility coverage (which we got, which we skipped, why).
- Any data shape mismatches with OH/PA that required normalization.
- `Provider` key shape (integer IDs vs. string codes).
- `git diff --stat` of the change.
- Total run time of `python energy_scraper.py` to confirm we're not blowing the workflow budget.
