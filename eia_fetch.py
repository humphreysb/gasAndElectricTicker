"""
Fetch Ohio residential electric + natural gas monthly average retail prices
from the EIA Open Data API (https://www.eia.gov/opendata/).

Writes eiaData.parquet with columns: Date, electric (bool), rate.
Rate is in matching units to the rest of the project:
  - Electric: $/kWh  (EIA returns cents/kWh; divide by 100)
  - Natural Gas: $/MCF  (EIA returns $/thousand cubic feet directly)

API key: read from env var EIA_API_KEY, or ~/.eia_api_key file, or first CLI arg.
Sign up free at https://www.eia.gov/opendata/register.php
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
OUT_FILE = ROOT / "eiaData.parquet"

ELEC_URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
GAS_URL = "https://api.eia.gov/v2/natural-gas/pri/sum/data/"


def get_api_key():
    key = os.environ.get("EIA_API_KEY")
    if key:
        return key
    keyfile = Path.home() / ".eia_api_key"
    if keyfile.exists():
        return keyfile.read_text().strip()
    if len(sys.argv) > 1:
        return sys.argv[1]
    raise SystemExit(
        "EIA API key not found.\n"
        "  Set EIA_API_KEY env var, write key to ~/.eia_api_key, "
        "or pass as first arg.\n"
        "  Get a free key at https://www.eia.gov/opendata/register.php"
    )


def fetch_paged(url, params, max_pages=20):
    """EIA returns up to 5000 rows per call; page through with offset."""
    rows = []
    offset = 0
    length = 5000
    for _ in range(max_pages):
        p = dict(params)
        p["offset"] = offset
        p["length"] = length
        r = requests.get(url, params=p, timeout=60)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("response", {}).get("data", [])
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < length:
            break
        offset += length
        time.sleep(0.5)
    return rows


def fetch_ohio_electric_residential(api_key):
    params = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[0]": "price",
        "facets[stateid][]": "OH",
        "facets[sectorid][]": "RES",
        "start": "2001-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    return fetch_paged(ELEC_URL, params)


def fetch_ohio_gas_residential(api_key):
    # Series id for Ohio residential gas: PRI_SUM is the natural gas prices summary
    # facets: duoarea = SOH (state of Ohio), process = PRS (residential price)
    params = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[0]": "value",
        "facets[duoarea][]": "SOH",
        "facets[process][]": "PRS",
        "start": "2001-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    return fetch_paged(GAS_URL, params)


def main():
    key = get_api_key()
    print("Fetching Ohio residential electric monthly prices...")
    elec_rows = fetch_ohio_electric_residential(key)
    print(f"  got {len(elec_rows)} rows")

    print("Fetching Ohio residential natural gas monthly prices...")
    gas_rows = fetch_ohio_gas_residential(key)
    print(f"  got {len(gas_rows)} rows")

    records = []
    for r in elec_rows:
        period = r.get("period")
        price_cents_kwh = r.get("price")
        if period is None or price_cents_kwh in (None, ""):
            continue
        try:
            rate = float(price_cents_kwh) / 100.0  # cents/kWh → $/kWh
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "Date": pd.to_datetime(period),
                "electric": True,
                "rate": rate,
                "source": "EIA_OH_RES",
            }
        )

    for r in gas_rows:
        period = r.get("period")
        val = r.get("value")
        if period is None or val in (None, ""):
            continue
        try:
            rate = float(val)  # EIA gives $/Mcf directly for residential
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "Date": pd.to_datetime(period),
                "electric": False,
                "rate": rate,
                "source": "EIA_OH_RES",
            }
        )

    if not records:
        print("No data collected — check API key and endpoint params.")
        sys.exit(1)

    df = pd.DataFrame(records).sort_values(["electric", "Date"])
    df.to_parquet(OUT_FILE)
    e = df[df["electric"]]
    g = df[~df["electric"]]
    print(
        f"\nWrote {OUT_FILE.name}: {len(df)} rows  "
        f"({len(e)} electric, {len(g)} gas)"
    )
    if len(e):
        print(f"  electric: {e['Date'].min().date()} → {e['Date'].max().date()}")
    if len(g):
        print(f"  gas:      {g['Date'].min().date()} → {g['Date'].max().date()}")


if __name__ == "__main__":
    main()
