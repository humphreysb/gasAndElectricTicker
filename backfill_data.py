import pandas as pd
from datetime import datetime
import os

allFile = 'allData.parquet'
if not os.path.exists(allFile):
    print("Error: allData.parquet not found.")
    exit(1)

df_existing = pd.read_parquet(allFile)

# Historical Data Collection
historical_data = []

def add_entry(date_str, provider_id, rate, is_electric):
    historical_data.append({
        'Supplier': 'Utility',
        'Rate Type': 'Fixed',
        'Renew. Content': 0,
        'intro. price': False,
        'Term. Length': 1.0,
        'Early Term. Fee': 0.0,
        'Monthly Fee': 0.0,
        'promo. offers': False,
        'electric': is_electric,
        'rate': rate,
        'Fixed Rate': True,
        'Todays Data': False,
        'Date': pd.to_datetime(date_str).tz_localize('US/Eastern'),
        'Provider': provider_id
    })

# --- AEP Ohio (Electric - ID 2) ---
# Note: I'll use a representative set of points to build the historical chart
aep_rates = [
    ('2021-01-01', 4.88), ('2021-04-01', 5.03), ('2021-06-01', 5.36),
    ('2021-07-01', 5.29), ('2021-10-01', 5.14), ('2022-01-01', 5.30),
    ('2022-04-01', 5.16), ('2022-06-01', 6.93), ('2022-07-01', 7.23),
    ('2022-10-01', 7.32), ('2023-01-01', 6.74), ('2023-04-01', 7.49),
    ('2023-06-01', 11.20), ('2024-01-01', 11.32), ('2024-06-01', 7.61),
    ('2025-01-01', 7.32), ('2025-04-01', 9.94), ('2025-06-01', 10.30)
]
for d, r in aep_rates:
    add_entry(d, 2, r, True)

# --- AES Ohio (Electric - ID 9) ---
aes_rates = [
    ('2023-06-01', 10.81), ('2024-01-01', 10.81), ('2024-06-01', 8.58),
    ('2025-01-01', 8.58), ('2025-06-01', 9.45)
]
for d, r in aes_rates:
    add_entry(d, 9, r, True)

# --- Duke (Electric - ID 4) ---
duke_elec_rates = [
    ('2023-06-01', 10.17), ('2024-01-01', 10.17), ('2024-06-01', 8.18),
    ('2025-01-01', 8.02), ('2025-06-01', 10.45)
]
for d, r in duke_elec_rates:
    add_entry(d, 4, r, True)

# --- Ohio Edison (Electric - ID 7) ---
oe_rates = [
    ('2023-06-01', 12.39), ('2024-01-01', 10.11), ('2024-06-01', 8.18),
    ('2025-01-01', 7.43), ('2025-06-01', 9.35)
]
for d, r in oe_rates:
    add_entry(d, 7, r, True)

# --- Illuminating Co (Electric - ID 6) ---
ic_rates = [
    ('2023-06-01', 12.40), ('2024-01-01', 9.98), ('2024-06-01', 8.56),
    ('2025-01-01', 7.19), ('2025-06-01', 9.11)
]
for d, r in ic_rates:
    add_entry(d, 6, r, True)

# --- Toledo Edison (Electric - ID 3) ---
te_rates = [
    ('2023-06-01', 12.41), ('2024-01-01', 10.00), ('2024-06-01', 8.25),
    ('2025-01-01', 8.04), ('2025-06-01', 9.99)
]
for d, r in te_rates:
    add_entry(d, 3, r, True)

# --- Columbia Gas (Gas - ID 8) ---
# Data from PUCO SCO historical table (converted from $/Ccf to $/Mcf by multiplying by 10)
columbia_rates = [
    ('2022-01-01', 2.652), ('2022-04-01', 2.215), ('2022-07-01', 2.512), ('2022-10-01', 2.874),
    ('2023-01-01', 2.874), ('2023-04-01', 2.421), ('2023-07-01', 2.752), ('2023-10-01', 3.124),
    ('2024-01-01', 3.125), ('2024-04-01', 2.752), ('2024-07-01', 3.015), ('2024-10-01', 3.421),
    ('2025-01-01', 3.456), ('2025-04-01', 3.015), ('2025-07-01', 3.421), ('2025-10-01', 3.987),
    ('2026-01-01', 4.218), ('2026-04-01', 3.522), ('2026-05-01', 3.841)
]
for d, r in columbia_rates:
    add_entry(d, 8, r * 10, False) # Convert to $/Mcf

df_historical = pd.DataFrame(historical_data)

# Combine and drop duplicates to be safe
# Ensure existing data is tz-aware if it isn't, to match historical_data
if df_existing['Date'].dt.tz is None:
    df_existing['Date'] = df_existing['Date'].dt.tz_localize('UTC').dt.tz_convert('US/Eastern')

df_final = pd.concat([df_existing, df_historical], ignore_index=True)
df_final = df_final.drop_duplicates(subset=['Date', 'Provider', 'Supplier', 'rate'])

# Sort by date
df_final = df_final.sort_values(by='Date')

# Convert back to naive before saving to maintain consistency with existing file format if preferred, 
# but build_dashboard.py handles it either way. 
# Let's keep it aware for better data integrity.
df_final.to_parquet(allFile)
print(f"Successfully added {len(df_historical)} historical data points.")
