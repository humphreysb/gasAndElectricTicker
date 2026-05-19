"""Daily scraper dispatcher.

Iterates over every registered per-state scraper, tags rows with the
scraper's state code, and appends to allData.parquet. Each per-state
scraper lives under `scrapers/` and is wired up in `scrapers/__init__.py`.
"""

import os
import sys

import pandas as pd

from scrapers import ALL_SCRAPERS

ALL_FILE = 'allData.parquet'


def main():
    if os.path.exists(ALL_FILE):
        df_all = pd.read_parquet(ALL_FILE)
        df_all['Todays Data'] = False
        if 'state' not in df_all.columns:
            df_all['state'] = 'OH'  # backfill rows scraped before the column existed
    else:
        df_all = None

    new_frames = []
    for scraper in ALL_SCRAPERS:
        state = scraper.STATE
        print(f"[scrape] {state}: starting", flush=True)
        try:
            df = scraper.scrape()
        except Exception as exc:
            print(f"[scrape] {state}: FAILED — {exc}", file=sys.stderr, flush=True)
            continue
        df['state'] = state
        new_frames.append(df)
        print(f"[scrape] {state}: pulled {len(df)} rows", flush=True)

    if not new_frames:
        print("[scrape] no scrapers returned data; aborting write", file=sys.stderr, flush=True)
        sys.exit(1)

    df_new = pd.concat(new_frames, ignore_index=True)
    df_combined = df_new if df_all is None else pd.concat([df_all, df_new], ignore_index=True)
    df_combined.to_parquet(ALL_FILE)
    print(f"[scrape] wrote {len(df_combined)} total rows to {ALL_FILE}", flush=True)


if __name__ == '__main__':
    main()
