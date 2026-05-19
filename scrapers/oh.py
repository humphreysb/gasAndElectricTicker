"""Ohio scraper — pulls today's rates from the Energy Choice Ohio
"Apples to Apples" marketplace (https://energychoice.ohio.gov).

The scraper hits one URL per (fuel, delivery utility) pair and parses
the returned HTML table directly with pandas.read_html. Each
delivery utility is identified by its TerritoryId; the IDs and friendly
names are kept in providers.STATES['OH'].
"""

from datetime import datetime
from io import StringIO

import pandas as pd
import pytz
import requests
import urllib3

import providers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

STATE = 'OH'
_URL = 'https://energychoice.ohio.gov/ApplesToApplesComparision.aspx'


def _get_supplier_data(params):
    response = requests.get(
        _URL,
        params=params,
        headers={'User-Agent': 'Mozilla/5.0'},
        verify=False,
    )
    response.raise_for_status()
    html_wrapped = StringIO(response.text)
    df = pd.read_html(html_wrapped)[0]

    df = df.rename(columns={'term length': 'Term. Length'})
    df.columns = df.columns.str.strip()

    df['Term. Length'] = df['Term. Length'].str.extract(r'(\d+)').astype(float)

    # Gas suppliers report in either $/Mcf or $/Ccf; normalize to $/Mcf.
    if params['Category'] == 'Electric':
        key, multiplier = '$/kWh', 1
        df['electric'] = True
    else:
        if '$/Mcf' in df.columns:
            key, multiplier = '$/Mcf', 1
        else:
            key, multiplier = '$/Ccf', 0.1
        df['electric'] = False
    df['rate'] = pd.to_numeric(df[key]) / multiplier
    df = df.drop(key, axis=1)

    df['Renew. Content'] = pd.to_numeric(
        df['Renew. Content'].str.replace('%', '', regex=False), errors='coerce'
    )

    df['Early Term. Fee'] = df['Early Term. Fee'].str.replace('$', '', regex=False)
    df['Early Term. Fee'] = df['Early Term. Fee'].str.replace('details', '', regex=False)
    df['Early Term. Fee'] = pd.to_numeric(df['Early Term. Fee'], errors='coerce')

    for col in ('intro. price', 'promo. offers'):
        s = df[col].astype(str)
        df.loc[s.str.contains('No', na=False), col] = False
        df.loc[s.str.contains('Yes', na=False), col] = True

    df['Monthly Fee'] = pd.to_numeric(
        df['Monthly Fee'].str.replace('$', '', regex=False), errors='coerce'
    )

    df = df.drop('Click to  Compare', axis=1)

    df['Fixed Rate'] = df['Rate Type'].astype(str).str.contains('Fixed', na=False)
    df['Todays Data'] = True
    df['Supplier'] = df['Supplier'].astype(str).str.split('(').str[0]
    df['Date'] = datetime.now(pytz.timezone('US/Eastern'))
    df['Provider'] = params['TerritoryId']

    return df


def _get_category(category, utility_map):
    pulls = []
    for territory_id in utility_map:
        pulls.append(_get_supplier_data({
            'Category': category,
            'TerritoryId': territory_id,
            'RateCode': 1,
        }))
    return pd.concat(pulls, ignore_index=True)


def scrape():
    """Return today's combined electric + gas rows for Ohio."""
    util = providers.for_state(STATE)
    return pd.concat(
        [_get_category('Electric', util['elec']), _get_category('Gas', util['gas'])],
        ignore_index=True,
    )
