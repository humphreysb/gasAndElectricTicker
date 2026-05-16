"""
Merge historicalData.parquet (from Wayback backfill) into allData.parquet.
Idempotent — dedupes on (Date_to_day, Provider, electric, Supplier, Term. Length, rate).
Preserves any existing rows (including the Gemini-added utility default rates).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
ALL_FILE = ROOT / "allData.parquet"
HIST_FILE = ROOT / "historicalData.parquet"


def main():
    if not HIST_FILE.exists():
        print(f"No {HIST_FILE.name} found. Run wayback_backfill.py first.")
        return
    all_df = pd.read_parquet(ALL_FILE)
    hist_df = pd.read_parquet(HIST_FILE)
    print(f"Existing allData.parquet: {len(all_df):,} rows")
    print(f"Historical (Wayback):     {len(hist_df):,} rows")

    # Align columns — fill missing with sensible defaults
    for col in all_df.columns:
        if col not in hist_df.columns:
            hist_df[col] = None
    hist_df = hist_df[all_df.columns]

    # Concat
    merged = pd.concat([all_df, hist_df], ignore_index=True)

    # Dedupe on day-resolution + key fields
    merged["_day"] = pd.to_datetime(merged["Date"]).dt.tz_localize(None).dt.normalize()
    key_cols = ["_day", "Provider", "electric", "Supplier", "Term. Length", "rate"]
    before = len(merged)
    merged = merged.drop_duplicates(subset=key_cols, keep="first")
    after = len(merged)
    merged = merged.drop(columns=["_day"])

    print(f"After dedupe: {after:,} rows (dropped {before - after:,} duplicates)")

    # Backup existing
    backup = ALL_FILE.with_suffix(".parquet.bak")
    all_df.to_parquet(backup)
    print(f"Backup of original allData → {backup.name}")

    merged.to_parquet(ALL_FILE)
    print(f"Wrote merged {ALL_FILE.name}: {len(merged):,} rows")
    print(
        f"  date range: {pd.to_datetime(merged['Date']).min()} → "
        f"{pd.to_datetime(merged['Date']).max()}"
    )


if __name__ == "__main__":
    main()
