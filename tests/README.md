# Tests

Lightweight smoke tests that catch the most common ways the multi-state
pipeline breaks. No network calls — these run in milliseconds.

## Run them

From the repo root:

```bash
python -m unittest discover tests
```

Or one file at a time:

```bash
python -m unittest tests.test_scraper_interface
python -m unittest tests.test_data_schema
```

## What's covered

### `test_scraper_interface.py`
- Every module registered in `scrapers/__init__.py` exposes `STATE` (uppercase 2-letter string) and a callable `scrape()`.
- Every scraper's `STATE` has a matching entry in `providers.STATES`.
- Every state's provider entry has non-empty `elec` and `gas` dicts.
- `providers.elec` / `providers.gas` still resolve to Ohio (backward compatibility shim).
- `STATE` codes are unique across scrapers.

### `test_data_schema.py`
- `allData.parquet` contains every column the dashboard builder reads.
- `state` is never null.
- `electric` is boolean, `rate` is numeric, `Date` is datetime.
- `Todays Data` rows for a given state all share the same date (catches the bug where a prior run didn't reset the flag).

## What's NOT covered (deliberate)

- Live scraping. These tests never hit `papowerswitch.com` or any other live site — those would be flaky and slow. Scraper output is validated implicitly by the schema test after a real run.
- Dashboard HTML rendering. The HTML is a build artifact; testing its exact contents would be brittle.
- Plotly chart correctness.

When something does break in production, the daily GitHub Action's logs will surface it. These tests are the cheap pre-flight check.
