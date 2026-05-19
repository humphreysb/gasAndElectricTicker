# Task brief: Add a New York scraper to RateSavvy

Run after IL ships. Same shape as the MD brief; this is the NY-specific notes.

## Site

- **Both fuels:** http://www.powertochoose.ny.gov — run by NY Department of Public Service. **Single site, both fuels.** Different from the OH/PA/MD pattern where each fuel has its own site.

## Residential utilities

**Electric:**
- Con Edison (NYC + Westchester)
- National Grid (upstate, mostly)
- NYSEG (New York State Electric & Gas, central + western)
- RG&E (Rochester Gas & Electric)
- Orange & Rockland (lower Hudson Valley)
- Central Hudson (Hudson Valley)

**Gas:**
- Con Edison
- National Grid (downstate + upstate divisions are separate — confirm in the site's filter)
- NYSEG
- Central Hudson
- KeySpan / National Grid Long Island (if surfaced separately)

## What's different

- **Six EDCs and at least four LDCs.** This is the most utilities of any state we're onboarding. Take a `time.sleep(1)` seriously per request — total scrape time will already be ~12+ seconds.
- **Single comparison site for both fuels.** The scraper's `_get_category` helper can probably share one URL builder with a `Category` parameter, like Ohio's.
- **NY's filter UI tends to be JS-heavy.** Investigate carefully whether the rate table is in the initial HTML response or loaded via XHR. **If it's XHR, find the JSON endpoint and call that directly** — same approach the PA scraper used. Do not introduce Selenium.

## Deliverable

- `scrapers/ny.py`.
- `providers.STATES['NY']` populated with both fuels.
- `STATE_CONFIG['NY']` in `build_dashboard.py` with `ny-electric_dashboard.html` and `ny-gas_dashboard.html` and reasonable thresholds (Con Ed PTC ~$0.12/kWh, Upstate cheaper around $0.08; gas Mcf prices vary widely seasonally — use $12 as a placeholder, refine after first scrape).

## Out of scope

Same exclusions as `MD_SCRAPER_BRIEF.md`.
