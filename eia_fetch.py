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


def fetch_electric_residential(api_key, state_id):
    params = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[0]": "price",
        "facets[stateid][]": state_id,
        "facets[sectorid][]": "RES",
        "start": "2019-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    return fetch_paged(ELEC_URL, params)


def fetch_gas_residential(api_key, state_id):
    # facets: duoarea = S + state_id (e.g. SOH, SPA), process = PRS (residential price)
    params = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[0]": "value",
        "facets[duoarea][]": f"S{state_id}",
        "facets[process][]": "PRS",
        "start": "2019-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
    }
    return fetch_paged(GAS_URL, params)


def main():
    key = get_api_key()
    records = []
    
    for state_id in ["OH", "PA"]:
        print(f"Fetching {state_id} residential electric monthly prices...")
        elec_rows = fetch_electric_residential(key, state_id)
        print(f"  got {len(elec_rows)} rows")

        for r in elec_rows:
            period = r.get("period")
            price_cents_kwh = r.get("price")
            if period is None or price_cents_kwh in (None, ""):
                continue
            try:
                rate = float(price_cents_kwh) / 100.0  # cents/kWh → $/kWh
            except (TypeError, ValueError):
                continue
            records.append({
                "Date": pd.to_datetime(period),
                "electric": True,
                "rate": rate,
                "source": f"EIA_{state_id}_RES",
                "state": state_id
            })

        print(f"Fetching {state_id} residential natural gas monthly prices...")
        gas_rows = fetch_gas_residential(key, state_id)
        print(f"  got {len(gas_rows)} rows")

        for r in gas_rows:
            period = r.get("period")
            val = r.get("value")
            if period is None or val in (None, ""):
                continue
            try:
                rate = float(val)
            except (TypeError, ValueError):
                continue
            records.append({
                "Date": pd.to_datetime(period),
                "electric": False,
                "rate": rate,
                "source": f"EIA_{state_id}_RES",
                "state": state_id
            })

    if not records:
        print("No data collected — check API key and endpoint params.")
        sys.exit(1)

    df = pd.DataFrame(records).sort_values(["state", "electric", "Date"])
    df.to_parquet(OUT_FILE)
    print(f"\nWrote {OUT_FILE.name}: {len(df)} rows across {df['state'].nunique()} states")


if __name__ == "__main__":
    main()
