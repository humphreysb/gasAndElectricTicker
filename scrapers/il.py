"""Illinois scraper — pulls today's residential rates from the Illinois
Commerce Commission's "PlugIn Illinois" comparison tools.

Electric offers are served by the PlugIn site as a tabular iframe at
icc.illinois.gov/plugin/offers, keyed by the utility's `said` ID:

    said=1  ComEd
    said=2  Ameren Illinois Rate Zone I
    said=3  Ameren Illinois Rate Zone II
    said=4  Ameren Illinois Rate Zone III
    said=5  MidAmerican

Gas offers live on a separate ICC endpoint at
icc.illinois.gov/natural-gas-choice/products, also keyed by `said`:

    said=1  North Shore Gas
    said=2  Nicor Gas
    said=3  Peoples Gas

Both endpoints return a single rendered HTML table parseable by
pandas.read_html. Units differ: electric is cents per kWh (we convert
to dollars per kWh); gas is dollars per therm (we convert to dollars
per Mcf using the standard 1 Mcf ≈ 10.37 therms factor so values line
up with Ohio's and Pennsylvania's units).

The first row of each electric table is the utility's Price to Compare
(default supply rate). It has no term length, which is how we detect
it; we tag it Supplier='Utility' to match Ohio's convention so the
dashboard's PTC-based comparisons still work.
"""
from datetime import datetime
from io import StringIO
import re
import time

import pandas as pd
import pytz
import requests

import providers

STATE = 'IL'

_ELEC_URL = 'https://icc.illinois.gov/plugin/offers'
_GAS_URL = 'https://www.icc.illinois.gov/natural-gas-choice/products'

# 1 Mcf ≈ 10.37 therms (EIA standard conversion factor)
_THERMS_PER_MCF = 10.37

_NUM_RE = re.compile(r'(\d*\.\d+|\d+)')
_FEE_RE = re.compile(r'\$?\s*(\d*\.\d+|\d+)')
# Supplier cells have the shape: "<phone> <plan name>  +"; strip phone prefix and trailing "+".
_PHONE_PREFIX_RE = re.compile(r'^[\(\)\d\-\.\s]+')


def _extract_first_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    m = _NUM_RE.search(str(value))
    return float(m.group(1)) if m else None


def _extract_dollar_amount(value):
    """Pull a numeric dollar amount out of strings like '$0', 'none', '$48.30', NaN."""
    if value is None:
        return 0.0
    s = str(value).strip().lower()
    if s in ('', 'nan', 'none', 'n/a', '-'):
        return 0.0
    m = _FEE_RE.search(s)
    return float(m.group(1)) if m else 0.0


def _classify_rate_type(price_text):
    """Return (is_fixed, normalized_rate_type)."""
    s = str(price_text or '').lower()
    if 'fixed' in s:
        return True, 'Fixed Rate'
    if 'variable' in s:
        return False, 'Variable Rate'
    if 'introduc' in s or 'intro' in s:
        return False, 'Introductory'
    return False, str(price_text or '').strip()


def _scrape_electric(said):
    """Return today's electric rows for one Illinois EDC (by `said` id)."""
    r = requests.get(_ELEC_URL, params={'said': said},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    if not tables:
        return pd.DataFrame()
    df = tables[0]
    # Flatten MultiIndex columns to the most specific (level 1) label.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[-1]).strip() for c in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]

    # Drop placeholder/empty rows (some service areas like MidAmerican render
    # a stub row with no supplier).
    df = df[df['Supplier'].notna() & (df['Supplier'].astype(str).str.strip() != '')].copy()
    if df.empty:
        return pd.DataFrame()

    # Map IL columns → shared schema.
    out = pd.DataFrame()
    # Strip the leading phone number and the trailing " +" UI indicator,
    # leaving just the plan/supplier name (e.g. "AP&G Fixed Rate").
    out['Supplier'] = (df['Supplier'].astype(str)
                       .str.replace(_PHONE_PREFIX_RE, '', regex=True)
                       .str.replace(r'\s*\+\s*$', '', regex=True)
                       .str.strip())
    out['Rate Type'] = df['Price in cents per kWh'].astype(str).str.strip()
    # Electric price is cents/kWh — convert to $/kWh.
    out['rate'] = df['Price in cents per kWh'].apply(_extract_first_float) / 100.0
    out['Monthly Fee'] = df['Additional Monthly Fees'].apply(_extract_dollar_amount)
    out['Term. Length'] = pd.to_numeric(df['Term (Mo.)'], errors='coerce')
    out['Renew. Content'] = df['Description'].astype(str).str.extract(r'(\d+)\s*%', expand=False)
    out['Renew. Content'] = pd.to_numeric(out['Renew. Content'], errors='coerce').fillna(0)
    descriptions = df['Description'].astype(str)
    out['intro. price'] = descriptions.str.contains('intro', case=False, regex=False)
    out['promo. offers'] = descriptions.str.contains('promo', case=False, regex=False)
    # IL doesn't surface ETF in this table; assume 0 unless description says otherwise.
    out['Early Term. Fee'] = 0.0

    # Fixed/variable from the rate-type text.
    classifications = out['Rate Type'].apply(_classify_rate_type)
    out['Fixed Rate'] = classifications.apply(lambda t: t[0])
    out['Rate Type'] = classifications.apply(lambda t: t[1])

    # First row with no term is the utility's PTC — tag accordingly.
    is_ptc = out['Term. Length'].isna()
    out.loc[is_ptc, 'Supplier'] = 'Utility'

    out['electric'] = True
    out['Todays Data'] = True
    out['Date'] = datetime.now(pytz.timezone('US/Eastern'))
    out['Provider'] = int(said)
    # Drop rows whose price couldn't be parsed (e.g. "Call for custom quote")
    # or that report a literal $0 rate (data-entry errors by suppliers).
    out = out[out['rate'].notna() & (out['rate'] > 0)].reset_index(drop=True)
    return out


def _scrape_gas(said):
    """Return today's gas rows for one Illinois NGDC (by `said` id)."""
    r = requests.get(_GAS_URL, params={'said': said, 'mid': 'R'},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    if len(tables) < 2:
        # Page renders a small "current utility supply charge" table even when
        # there are zero supplier offers; only the second table holds offers.
        return pd.DataFrame()
    df = tables[1]
    df.columns = [str(c).strip() for c in df.columns]

    out = pd.DataFrame()
    out['Supplier'] = df['Supplier'].astype(str).str.strip()
    out['Rate Type'] = df["Today's Price per therm"].astype(str).str.strip()
    # Gas price is $/therm — convert to $/Mcf to align with OH/PA.
    therms_price = df["Today's Price per therm"].apply(_extract_first_float)
    out['rate'] = therms_price * _THERMS_PER_MCF
    out['Monthly Fee'] = df['Additional Fees'].apply(_extract_dollar_amount)
    out['Term. Length'] = df['Term'].astype(str).apply(_extract_first_float)
    out['Early Term. Fee'] = df['Termination Fees'].apply(_extract_dollar_amount)
    out['Renew. Content'] = df['Description'].astype(str).str.extract(r'(\d+)\s*%', expand=False)
    out['Renew. Content'] = pd.to_numeric(out['Renew. Content'], errors='coerce').fillna(0)
    descriptions = df['Description'].astype(str)
    out['intro. price'] = descriptions.str.contains('intro', case=False, regex=False)
    out['promo. offers'] = descriptions.str.contains('promo', case=False, regex=False)

    classifications = out['Rate Type'].apply(_classify_rate_type)
    out['Fixed Rate'] = classifications.apply(lambda t: t[0])
    out['Rate Type'] = classifications.apply(lambda t: t[1])

    out['electric'] = False
    out['Todays Data'] = True
    out['Date'] = datetime.now(pytz.timezone('US/Eastern'))
    out['Provider'] = int(said)
    # Drop rows whose price couldn't be parsed (variable-rate placeholder text
    # like "Visit our website" returns NaN).
    out = out[out['rate'].notna() & (out['rate'] > 0)].reset_index(drop=True)
    return out


def scrape():
    """Return today's combined electric + gas rows for Illinois."""
    util = providers.for_state(STATE)
    frames = []
    for said in util['elec']:
        try:
            frames.append(_scrape_electric(said))
        except Exception as exc:
            print(f"[scrape] IL electric said={said} failed: {exc}", flush=True)
        time.sleep(1)
    for said in util['gas']:
        try:
            frames.append(_scrape_gas(said))
        except Exception as exc:
            print(f"[scrape] IL gas said={said} failed: {exc}", flush=True)
        time.sleep(1)
    return pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
