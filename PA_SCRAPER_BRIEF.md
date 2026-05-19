# Task brief: Add a Pennsylvania scraper to RateSavvy

You are working in the `~/projects/brad-energy` repo (RateSavvy — energy rate tracker). The codebase has just been refactored to support multiple states. Ohio is wired up; your job is to add Pennsylvania as state #2 and validate the multi-state architecture end-to-end.

## What "done" looks like

After your work, running `python energy_scraper.py` should pull today's residential electricity AND natural gas rates from Pennsylvania's official comparison sites, append them to `allData.parquet` with `state='PA'`, and `python build_dashboard.py` should emit `pa-electric_dashboard.html` and `pa-gas_dashboard.html` in addition to the existing Ohio files. The state dropdown at the top of every dashboard should let users switch between OH and PA, and switching should navigate to the right file.

No edits to `build_dashboard.py` should be needed beyond a single `STATE_CONFIG` entry. If you find yourself rewriting dashboard logic, stop — the architecture is supposed to absorb you. Ask the user.

## Read these first (don't skip)

In this order:

1. `MARKET_EXPANSION.md` — the plan. Pennsylvania is the top priority for a reason.
2. `scrapers/__init__.py` — the registry. You'll add to `ALL_SCRAPERS`.
3. `scrapers/oh.py` — your template. The PA scraper must expose the same two names (`STATE`, `scrape()`) and return rows with the same column shape.
4. `providers.py` — you'll add a `'PA'` entry under `STATES`.
5. `build_dashboard.py` lines 1806–1860 (the EXECUTION block + `STATE_CONFIG`) — you'll add one PA entry.
6. `energy_scraper.py` — the dispatcher. Glance at it to confirm you understand what it expects from each scraper module.

## The PA sites

Pennsylvania's comparison sites are run by the PA Public Utility Commission and mirror Ohio's "Apples to Apples" model — separate sites for electric and gas, both with structured rate tables filterable by delivery utility (called "EDC" in PA for electric, "NGDC" for gas).

- **Electric:** https://www.papowerswitch.com
- **Gas:** https://www.papagasswitch.com (verify — spelling may be `pagasswitch.com`)

### Pennsylvania delivery utilities

**Electric EDCs (residential):**
- PECO Energy
- PPL Electric Utilities
- Duquesne Light
- Met-Ed (FirstEnergy)
- Penelec (FirstEnergy)
- Penn Power (FirstEnergy)
- West Penn Power (FirstEnergy)
- Citizens' Electric of Lewisburg
- Pike County Light & Power
- Wellsboro Electric
- UGI Utilities (Electric Division)

**Gas NGDCs (residential):**
- UGI Utilities
- Columbia Gas of Pennsylvania
- PECO Energy (gas)
- Peoples Natural Gas
- Peoples Gas Company (legacy "Equitable" service area)
- National Fuel Gas
- Philadelphia Gas Works (PGW) — note: PGW does NOT participate in retail choice
- Valley Energy

For the first pass, focus on the **major utilities** (PECO, PPL, Duquesne, the four FirstEnergy subsidiaries for electric; UGI, Columbia, Peoples, National Fuel for gas). You can omit small utilities (Wellsboro, Citizens', Pike, Valley) if their data is awkward to scrape — just leave a TODO.

## Required column shape

Your `scrape()` MUST return a `pd.DataFrame` with these exact columns (same as `scrapers/oh.py`):

| Column | Type | Notes |
|---|---|---|
| `Supplier` | str | Cleaned supplier name (split on `(` and take first part) |
| `Rate Type` | str | Source-provided string |
| `Renew. Content` | float | Percent renewable, 0–100, numeric |
| `intro. price` | bool | True/False |
| `Term. Length` | float | Months, numeric (PA may format as "12 mo" or "12 months" — strip non-digits) |
| `Early Term. Fee` | float | Dollars |
| `Monthly Fee` | float | Dollars |
| `promo. offers` | bool | True/False |
| `electric` | bool | True for electric rows, False for gas |
| `rate` | float | Price per kWh ($/kWh) for electric, per Mcf ($/Mcf) for gas. **If gas site reports $/Ccf, divide by 0.1 to convert to $/Mcf so it matches Ohio's unit.** |
| `Fixed Rate` | bool | True if `Rate Type` contains "Fixed" |
| `Todays Data` | bool | Always True on freshly scraped rows |
| `Date` | datetime | `datetime.now(pytz.timezone('US/Eastern'))` |
| `Provider` | str or int | The utility identifier from PA's site (e.g. the EDC name or ID). Whatever you use here, it must match a key you add to `providers.STATES['PA']['elec']` (or `['gas']`) so the dashboard can render the utility name. |

Do NOT add a `state` column — the dispatcher (`energy_scraper.py`) adds it automatically.

## Implementation steps

### Step 1 — Investigate the PA sites

Before writing code, figure out:

1. Are rate tables rendered server-side (HTML you can `pd.read_html` directly) or client-side (JS-rendered, needs a headless browser)?
2. What's the URL pattern? Does it accept a query string like `?edc=PECO`, or is it a POST with form data, or does it set a session cookie based on ZIP?
3. Are residential rates filterable, or do you get commercial mixed in?

Use `curl` to fetch a page and `grep` for `<table` to check whether the table HTML comes back in the initial response. If it does, you're in pandas-territory. If not, you'll need to inspect the page in a browser, find the XHR call that loads the rate JSON/HTML, and hit that endpoint directly. **Do not introduce Selenium or Playwright** — keep the dependency footprint identical to Ohio's (`requests` + `pandas`).

If the data is truly only reachable via a headless browser, stop and report back to the user — that's a different architectural decision.

### Step 2 — Write `scrapers/pa.py`

Use `scrapers/oh.py` as the template. Structure:

```python
"""Pennsylvania scraper — pulls today's rates from PAPowerSwitch (electric)
and PAGasSwitch (gas)."""
from datetime import datetime
from io import StringIO
import pandas as pd
import pytz
import requests

import providers

STATE = 'PA'
_ELEC_URL = 'https://www.papowerswitch.com/...'  # confirm
_GAS_URL  = 'https://www.papagasswitch.com/...'  # confirm

def _get_supplier_data(category, utility):
    # ... fetch + parse one utility's table ...
    return df

def _get_category(category, utility_map):
    return pd.concat([_get_supplier_data(category, u) for u in utility_map], ignore_index=True)

def scrape():
    util = providers.for_state(STATE)
    return pd.concat([_get_category('Electric', util['elec']),
                      _get_category('Gas',      util['gas'])],
                     ignore_index=True)
```

Make every column transformation match Ohio's so the union plays nicely in `allData.parquet`. If PA's site uses different column names, rename them in your parser (Ohio renames `term length` → `Term. Length` in the same way).

### Step 3 — Wire PA into the registry

Three small edits:

1. **`providers.py`** — add a `'PA'` entry under `STATES`:
   ```python
   'PA': {
       'elec': {'PECO': 'PECO Energy', 'PPL': 'PPL Electric Utilities', ...},
       'gas':  {'UGI': 'UGI Utilities', 'Columbia': 'Columbia Gas of PA', ...},
   },
   ```
   The key shape (string or int) must match whatever the PA scraper writes into the `Provider` column.

2. **`scrapers/__init__.py`** — register the module:
   ```python
   from . import oh, pa
   ALL_SCRAPERS = [oh, pa]
   ```

3. **`build_dashboard.py`** — add to `STATE_CONFIG` (search for that constant):
   ```python
   'PA': {
       'name': 'Pennsylvania',
       'elec_file': 'pa-electric_dashboard.html',
       'gas_file':  'pa-gas_dashboard.html',
       'elec_threshold': 0.09,   # tune based on PA's typical PTC
       'gas_threshold':  3.00,
   },
   ```

### Step 4 — Test

```bash
source .venv/bin/activate
python energy_scraper.py   # should print "[scrape] OH:" and "[scrape] PA:" lines; writes parquet
python build_dashboard.py  # should emit pa-electric_dashboard.html + pa-gas_dashboard.html
```

Open `pa-electric_dashboard.html` in a browser. Sanity-check the values against the live PAPowerSwitch site for one utility. Make sure the state dropdown lists both Ohio and Pennsylvania and that selecting Pennsylvania navigates to the PA file.

### Step 5 — Commit

```
git add scrapers/pa.py providers.py scrapers/__init__.py build_dashboard.py \
        allData.parquet pa-electric_dashboard.html pa-gas_dashboard.html \
        electric_dashboard.html gas_dashboard.html
git commit -m "Add Pennsylvania scraper (state #2)"
```

The Ohio HTML files may also change (the state dropdown picks up a new option) — that's expected; include them.

## Constraints

- **Do not change the column shape of `allData.parquet`.** PA rows must be append-compatible with Ohio rows.
- **Do not introduce new top-level dependencies.** Stick to `requests`, `pandas`, `pytz`, `urllib3`. If PA truly needs `selenium` or `playwright`, stop and ask.
- **Do not rewrite `build_dashboard.py`** beyond the `STATE_CONFIG` entry. The dashboard is supposed to be state-agnostic. If it isn't, that's a bug — report it.
- **Respect rate limiting.** Add a `time.sleep(1)` between utility requests on the PA site so we're not hammering it.
- **Be conservative with utility coverage.** If a small/unusual utility (PGW for gas, Wellsboro for electric, etc.) doesn't have a clean rate table, leave a `# TODO` comment and skip it. We can add the long tail later.

## Out of scope (do NOT do)

- Don't update README, MARKET_EXPANSION.md, or any other docs. The user will do that after reviewing.
- Don't add a `pa.py` file under any directory other than `scrapers/`.
- Don't push the branch or open a PR. Just commit locally.
- Don't update `CNAME` or anything Pages-related.

## Report back to the user with

- The exact PA URL patterns you used (so they can audit)
- Which utilities you covered and which you skipped (with reason)
- Whether you encountered any data shape mismatches with Ohio
- A one-line summary of `Provider` key shape (string codes, integer IDs, etc.) so they know what `providers.STATES['PA']` looks like
- The git diff stats (`git diff --stat`)

Good luck.
