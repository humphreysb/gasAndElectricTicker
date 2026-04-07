import requests
import pandas as pd
import urllib3
from datetime import date
from io import StringIO
import providers
from datetime import datetime
import os
import pytz

# Providers: First Energy, AEP, etc. You don;t get to choose
# Suppliers:  Best energy, etc.  You do get to choose 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_supplier_data(params):

    url = "https://energychoice.ohio.gov/ApplesToApplesComparision.aspx"

    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False
    )

    response.raise_for_status()

    html_wrapped = StringIO(response.text)
    tables = pd.read_html(html_wrapped)
    df = tables[0]


    # Clean up data set
    df = df.rename(columns={'term length': 'Term. Length'})
    df.columns = df.columns.str.strip()
    
    # Remove the "mo"
    df['Term. Length'] = df['Term. Length'].str.extract(r'(\d+)').astype(float) 

    # Fix that some supplier use Mcf vs Ccf
    if params["Category"] == "Electric":
        key = '$/kWh' 
        df['electric'] = True 
        a=1
    else:
        if '$/Mcf' in df.columns:
            key = '$/Mcf'
            a=1
        else:
            key = '$/Ccf'
            a=0.1
        df['electric'] = False 
    df['rate'] = pd.to_numeric(df[key])/a
    df = df.drop(key, axis=1)

    # Remove % and make numeric
    df['Renew. Content'] = pd.to_numeric(df['Renew. Content'].str.replace('%', '', regex=False), errors='coerce')

    # Convert Early term fee to numeric
    df['Early Term. Fee'] = df['Early Term. Fee'].str.replace('$', '', regex=False)
    df['Early Term. Fee'] = df['Early Term. Fee'].str.replace('details', '', regex=False)
    df['Early Term. Fee'] = df['Early Term. Fee'] = pd.to_numeric(df['Early Term. Fee'], errors='coerce')


    mask = df['intro. price'].astype(str).str.contains('No', na=False)
    df.loc[mask, 'intro. price'] = False
    mask = df['intro. price'].astype(str).str.contains('Yes', na=False)
    df.loc[mask, 'intro. price'] = True

    mask = df['promo. offers'].astype(str).str.contains('No', na=False)
    df.loc[mask, 'promo. offers'] = False
    mask = df['promo. offers'].astype(str).str.contains('Yes', na=False)
    df.loc[mask, 'promo. offers'] = True

    # Remove $ and make numeric
    df['Monthly Fee'] = pd.to_numeric(df['Monthly Fee'].str.replace('$', '', regex=False), errors='coerce')

    #Extraneous Column
    df = df.drop('Click to  Compare', axis=1)

    # Booleanize Rate Type
    df['Fixed Rate'] = False
    mask = df['Rate Type'].astype(str).str.contains('Fixed', na=False)
    df.loc[mask, 'Fixed Rate'] = True

    # Add that this is fresh data
    df['Todays Data'] = True

    # Clip suppliers extraneous info
    df['Supplier'] = df['Supplier'].astype(str).str.split('(').str[0]

    df['Date'] = datetime.now(pytz.timezone('US/Eastern'))

    df['Provider'] = params['TerritoryId']

    return df

def get_data(category,providers):
    # Loop through suppliers
    firstPull = True
    for key in providers:
        params = {
        "Category": category,
        "TerritoryId": key,
        "RateCode": 1
        }

        df = get_supplier_data(params)

        if firstPull:
            dfNew = df
            firstPull = False
        else:
            dfNew = pd.concat([dfNew, df], ignore_index=True)

    return dfNew



# Load All Data File
allFile = 'allData.parquet'
if not os.path.exists(allFile):
    newFile = True
else:
    newFile = False
    dfAll = pd.read_parquet(allFile)
    dfAll['Todays Data'] = False

# Get New Gas and Electric Data
dfElec = get_data("Electric",providers.elec)
dfGas = get_data("Gas",providers.gas)
dfNew = pd.concat([dfElec, dfGas], ignore_index=True)

# Concat new data with old data
if newFile:
    dfAll = dfNew
else:
    dfAll = pd.concat([dfAll, dfNew], ignore_index=True)

# Write all data file
dfAll.to_parquet(allFile)