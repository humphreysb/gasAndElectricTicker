"""
Backfill historical Ohio Energy Choice supplier offers from the Wayback Machine.

Iterates each (category, territoryId) pair, queries the Wayback CDX API for
captured snapshots, fetches each snapshot via the `id_` raw-content endpoint,
and re-parses with the same logic the daily scraper uses.

Output: wayback_<category>_<territoryId>.parquet per utility, plus a merged
        historicalData.parquet at the end.

Resumable: per-utility files are written incrementally; re-run skips any
           (utility, timestamp) already present in its output file.

Polite: ~3s sleep between snapshot fetches.
"""
import json
import os
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import pytz
import requests

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "wayback_out"
OUT_DIR.mkdir(exist_ok=True)

CDX_URL = "https://web.archive.org/cdx/search/cdx"
ARCHIVE_URL = "https://web.archive.org/web/{ts}id_/{url}"  # id_ = original raw content

ELECTRIC_TIDS = [2, 3, 4, 6, 7, 9]
GAS_TIDS = [1, 8, 10, 11]

FETCH_SLEEP_SEC = 3.0
HEADERS = {"User-Agent": "Mozilla/5.0 (historical backfill, polite)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def list_snapshots(category, tid):
    """Return [(timestamp, original_url)] for captured snapshots of this URL."""
    target = (
        f"energychoice.ohio.gov/ApplesToApplesComparision.aspx"
        f"?Category={category}&TerritoryId={tid}&RateCode=1"
    )
    params = {
        "url": target,
        "matchType": "exact",
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",  # collapse to one per day
        "limit": 10000,
    }
    r = SESSION.get(CDX_URL, params=params, timeout=60)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        return []
    if not data or len(data) < 2:
        return []
    return [(row[1], row[2]) for row in data[1:]]


def parse_html(html, category, tid, ts):
    """Best-effort parse of an archived comparison page. Returns DataFrame or None."""
    try:
        tables = pd.read_html(StringIO(html))
    except Exception:
        return None
    if not tables:
        return None

    # Pick the largest table — the comparison grid usually dominates by rows × cols
    df = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    if df.shape[0] < 2 or df.shape[1] < 4:
        return None

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={"term length": "Term. Length"})

    if "Term. Length" not in df.columns:
        return None

    df["Term. Length"] = (
        df["Term. Length"].astype(str).str.extract(r"(\d+)").astype(float)
    )

    if category == "Electric":
        if "$/kWh" not in df.columns:
            return None
        key, scale = "$/kWh", 1.0
        df["electric"] = True
    else:
        if "$/Mcf" in df.columns:
            key, scale = "$/Mcf", 1.0
        elif "$/Ccf" in df.columns:
            key, scale = "$/Ccf", 0.1
        else:
            return None
        df["electric"] = False

    df["rate"] = pd.to_numeric(df[key].astype(str), errors="coerce") / scale
    df = df.drop(columns=[key])

    if "Renew. Content" in df.columns:
        df["Renew. Content"] = pd.to_numeric(
            df["Renew. Content"].astype(str).str.replace("%", "", regex=False),
            errors="coerce",
        )
    if "Early Term. Fee" in df.columns:
        s = df["Early Term. Fee"].astype(str).str.replace("$", "", regex=False)
        s = s.str.replace("details", "", regex=False)
        df["Early Term. Fee"] = pd.to_numeric(s, errors="coerce")
    if "intro. price" in df.columns:
        df["intro. price"] = (
            df["intro. price"].astype(str).str.contains("Yes", na=False)
        )
    if "promo. offers" in df.columns:
        df["promo. offers"] = (
            df["promo. offers"].astype(str).str.contains("Yes", na=False)
        )
    if "Monthly Fee" in df.columns:
        df["Monthly Fee"] = pd.to_numeric(
            df["Monthly Fee"].astype(str).str.replace("$", "", regex=False),
            errors="coerce",
        )
    if "Click to  Compare" in df.columns:
        df = df.drop(columns=["Click to  Compare"])
    if "Rate Type" in df.columns:
        df["Fixed Rate"] = (
            df["Rate Type"].astype(str).str.contains("Fixed", na=False)
        )
    else:
        df["Fixed Rate"] = False
    if "Supplier" in df.columns:
        df["Supplier"] = df["Supplier"].astype(str).str.split("(").str[0]
    else:
        return None  # no supplier column = unusable

    df["Todays Data"] = False
    dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
    df["Date"] = pytz.timezone("US/Eastern").localize(dt)
    df["Provider"] = tid

    # Drop rows with no rate
    df = df[df["rate"].notna()].copy()
    if df.empty:
        return None

    return df


def fetch_snapshot_html(ts, original_url):
    archive = ARCHIVE_URL.format(ts=ts, url=original_url)
    r = SESSION.get(archive, timeout=90)
    r.raise_for_status()
    return r.text


def process_one(category, tid, out_file):
    snapshots = list_snapshots(category, tid)
    print(f"[{category} tid={tid}] {len(snapshots)} snapshots after daily-collapse")
    if not snapshots:
        return

    existing_ts = set()
    rows = []
    if out_file.exists():
        try:
            existing = pd.read_parquet(out_file)
            rows.append(existing)
            existing_ts = set(
                pd.to_datetime(existing["Date"]).dt.strftime("%Y%m%d%H%M%S").tolist()
            )
            print(f"  resuming, {len(existing_ts)} already captured")
        except Exception:
            pass

    fetched = 0
    skipped = 0
    failed = 0
    for ts, url in snapshots:
        if ts in existing_ts:
            skipped += 1
            continue
        try:
            html = fetch_snapshot_html(ts, url)
            df = parse_html(html, category, tid, ts)
            if df is not None and not df.empty:
                rows.append(df)
                fetched += 1
                print(f"  {ts}: {len(df)} rows")
            else:
                failed += 1
                print(f"  {ts}: parse fail / empty")
        except Exception as e:
            failed += 1
            print(f"  {ts}: fetch error: {type(e).__name__}: {e}")

        # Save every 10 snapshots so we don't lose progress
        if fetched > 0 and fetched % 10 == 0:
            merged = pd.concat(rows, ignore_index=True)
            merged.to_parquet(out_file)
        time.sleep(FETCH_SLEEP_SEC)

    if rows:
        merged = pd.concat(rows, ignore_index=True)
        merged.to_parquet(out_file)
        print(f"  written: {len(merged):,} total rows in {out_file.name}")
    print(f"  done. fetched={fetched} skipped={skipped} failed={failed}\n")


def main():
    targets = (
        [("Electric", tid) for tid in ELECTRIC_TIDS]
        + [("NaturalGas", tid) for tid in GAS_TIDS]
    )
    if len(sys.argv) > 1:
        # filter to one category for testing: python wayback_backfill.py Electric 2
        cat = sys.argv[1]
        tid = int(sys.argv[2]) if len(sys.argv) > 2 else None
        targets = [(c, t) for (c, t) in targets if c == cat and (tid is None or t == tid)]
        print(f"Filtered to: {targets}")

    for category, tid in targets:
        out_file = OUT_DIR / f"wayback_{category}_{tid}.parquet"
        process_one(category, tid, out_file)

    # Merge all per-utility files into historicalData.parquet
    parts = []
    for f in sorted(OUT_DIR.glob("wayback_*.parquet")):
        try:
            parts.append(pd.read_parquet(f))
        except Exception as e:
            print(f"skip merge of {f}: {e}")
    if parts:
        merged = pd.concat(parts, ignore_index=True)
        merged.to_parquet(ROOT / "historicalData.parquet")
        print(
            f"\nMerged historicalData.parquet: {len(merged):,} rows, "
            f"{pd.to_datetime(merged['Date']).min()} to {pd.to_datetime(merged['Date']).max()}"
        )


if __name__ == "__main__":
    main()
