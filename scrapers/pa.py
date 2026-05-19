"""Pennsylvania scraper — pulls today's rates from PAPowerSwitch (electric)
and PAGasSwitch (gas)."""
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import pytz
import requests
import urllib3

import providers

# Disable SSL warnings (matching oh.py)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

STATE = 'PA'
_ELEC_BASE_URL = 'https://www.papowerswitch.com/shop-for-rates-results'
_GAS_BASE_URL = 'https://www.pagasswitch.com/shop-for-rates'

# Representative ZIP codes for each utility ID
_ELEC_ZIPS = {
    1182: '19103', # PECO
    1186: '18101', # PPL
    1180: '15201', # Duquesne
    1181: '19601', # Met-Ed
    1183: '16501', # Penelec
    1184: '16101', # Penn Power
    1189: '15601', # West Penn Power
    1187: '18701', # UGI
}

_GAS_ZIPS = {
    4425: '17601', # UGI
    4420: '15201', # Columbia
    4422: '19001', # PECO Gas
    4423: '15201', # Peoples
    4421: '16501', # National Fuel
    4424: '19103', # PGW
}

def _parse_numeric(value):
    if not value or pd.isna(value):
        return 0.0
    s = str(value).replace('$', '').replace(',', '').strip()
    if s.lower() == 'no' or s.lower() == 'none':
        return 0.0
    # Try to extract the first numeric value (integer or decimal)
    match = re.search(r'(\d+(\.\d+)?)', s)
    if match:
        return float(match.group(1))
    return 0.0

def _get_supplier_data(category, utility_id):
    is_electric = category == 'Electric'
    zip_code = _ELEC_ZIPS[utility_id] if is_electric else _GAS_ZIPS[utility_id]
    url = _ELEC_BASE_URL if is_electric else _GAS_BASE_URL
    
    params = {
        'zip' if is_electric else 'zipcode': zip_code,
        'distributor': utility_id,
        'servicetype': 'residential'
    }
    
    response = requests.get(
        url,
        params=params,
        headers={'User-Agent': 'Mozilla/5.0'},
        verify=False
    )
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    cards = soup.find_all('div', class_='supplier-card')
    
    rows = []
    for card in cards:
        # Extract data from data- attributes
        supplier = card.get('data-supplier', '').split('(')[0].strip()
        rate_type = card.get('data-ratestructure', '')
        
        # Renewable content: e.g. "100%" or "0%"
        renew_str = card.get('data-renewable', '0')
        renew_content = _parse_numeric(renew_str)
        
        intro_price = card.get('data-introprice', 'No').lower() == 'yes'
        
        term_str = card.get('data-termlength', '0')
        term_months = _parse_numeric(term_str)
        
        early_term_fee = _parse_numeric(card.get('data-cancelfee', '0'))
        monthly_fee = _parse_numeric(card.get('data-monthlyfee', '0'))
        promo_offers = card.get('data-newcustoffer', 'No').lower() == 'yes'
        
        rate_str = card.get('data-perkwh', '0')
        rate = _parse_numeric(rate_str)
            
        # Normalize gas rate to $/Mcf if needed.
        # Brief says: If gas site reports $/Ccf, divide by 0.1 to convert to $/Mcf.
        if not is_electric:
            rate = rate / 0.1
            
        rows.append({
            'Supplier': supplier,
            'Rate Type': rate_type,
            'Renew. Content': renew_content,
            'intro. price': intro_price,
            'Term. Length': term_months,
            'Early Term. Fee': early_term_fee,
            'Monthly Fee': monthly_fee,
            'promo. offers': promo_offers,
            'electric': is_electric,
            'rate': rate,
            'Fixed Rate': 'Fixed' in rate_type,
            'Todays Data': True,
            'Date': datetime.now(pytz.timezone('US/Eastern')),
            'Provider': utility_id
        })
        
    return pd.DataFrame(rows)

def _get_category(category, utility_map):
    pulls = []
    for utility_id in utility_map:
        pulls.append(_get_supplier_data(category, utility_id))
        time.sleep(1) # Respect rate limiting
    if not pulls:
        return pd.DataFrame()
    return pd.concat(pulls, ignore_index=True)

def scrape():
    """Return today's combined electric + gas rows for Pennsylvania."""
    util = providers.for_state(STATE)
    return pd.concat([
        _get_category('Electric', util['elec']),
        _get_category('Gas',      util['gas'])
    ], ignore_index=True)
