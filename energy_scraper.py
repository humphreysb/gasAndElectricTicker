import requests
import pandas as pd
import urllib3
from datetime import date
import csv
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_min_offer(params):


    url = "https://energychoice.ohio.gov/ApplesToApplesComparision.aspx"

    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False
    )

    tables = pd.read_html(response.text)
    df = tables[0]

    df.columns = df.columns.str.strip()

    df = df[df['Rate Type'].str.contains('Fixed', case=False)]
    df = df[df['intro. price'].str.contains('No', case=False)]

    df['Term. Length'] = df['Term. Length'].str.extract(r'(\d+)').astype(float)

    df = df[df['Term. Length'] >= 6]
    df = df[df['Early Term. Fee'].str.contains(r'\$0', regex=True)]
    df = df[df['Monthly Fee'].str.contains(r'\$0', regex=True)]
    df = df[df['promo. offers'].str.contains('No', case=False)]

    key = '$/kWh' if params["Category"] == "Electric" else '$/Mcf'

    df[key] = pd.to_numeric(df[key])

    row = df.loc[df[key].idxmin()]

    return row["Supplier"], row[key]


today = date.today()

elec_params = {
"Category": "Electric",
"TerritoryId": 6,
"RateCode": 1
}

gas_params = {
"Category": "NaturalGas",
"TerritoryId": 1,
"RateCode": 1
}

elec_supplier, elec_price = get_min_offer(elec_params)
gas_supplier, gas_price = get_min_offer(gas_params)

file = "elec_gas_data.csv"

if not os.path.exists(file):
    with open(file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date","ElectricPrice","ElectricSupplier","GasPrice","GasSupplier"])

with open(file, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([today, elec_price, elec_supplier, gas_price, gas_supplier])
