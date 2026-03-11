import requests
import pandas as pd
import urllib3
from datetime import date
import csv
import os
from io import StringIO

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_min_offer(params):


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

    df.columns = df.columns.str.strip()

    df = df[df['Rate Type'].str.contains('Fixed', case=False)]
    df = df[df['intro. price'].str.contains('No', case=False)]

    df['Term. Length'] = df['Term. Length'].str.extract(r'(\d+)').astype(float)

    df = df[df['Term. Length'] >= 6]
    df = df[df['Early Term. Fee'].str.contains(r'\$0', regex=True)]
    df = df[df['Monthly Fee'].str.contains(r'\$0', regex=True)]
    df = df[df['promo. offers'].str.contains('No', case=False)]

    
    a=1
    if params["Category"] == "Electric":
        key = '$/kWh' 
    else:
        if '$/Mcf' in df.columns:
            key = '$/Mcf'
            a=10
        else:
            key = '$/Ccf'



    df[key] = pd.to_numeric(df[key])/a

    row = df.loc[df[key].idxmin()]

    return row["Supplier"], row[key]



elecProviders = {9:'AES Power',
    2:'AEP',
    4:'Duke',
    7:'Ohio Edison',
    6:'Ilumminating Co',
    3:'Toledo Edison'}

gasProviders = {1:'Enbridge-Dominion',
                11:'Centerpoint',
                10:'Duke',
                8:'Columbia'}

file = "elec_gas_data.csv"

today = date.today()

data_list = []


for key in elecProviders:
    params = {
    "Category": "Electric",
    "TerritoryId": key,
    "RateCode": 1
    }

    supplier, price = get_min_offer(params)

    new_data = {"Date": today, 
                "ElecOrGas": 'elec', 
                'TerritoryId': key, 
                'Rate':price, 
                'Supplier':supplier}
    data_list.append(new_data)
    

for key in gasProviders:
    params = {
    "Category": "Gas",
    "TerritoryId": key,
    "RateCode": 1
    }

    supplier, price = get_min_offer(params)

    new_data = {"Date": today, 
                "ElecOrGas": 'gas', 
                'TerritoryId': key, 
                'Rate':price, 
                'Supplier':supplier}
    data_list.append(new_data)


df = pd.DataFrame(data_list)
dfFile = pd.read_csv(file)
df = pd.concat([dfFile, df])



df.to_csv(file, index=False) 



'''
if not os.path.exists(file):
    with open(file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date","ElectricPrice","ElectricSupplier","GasPrice","GasSupplier"])

with open(file, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([today, elec_price, elec_supplier, gas_price, gas_supplier])
'''
