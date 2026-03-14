import requests
import pandas as pd
import urllib3
from datetime import date
from io import StringIO
import providers
from datetime import datetime
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

    response.raise_for_status()

    html_wrapped = StringIO(response.text)
    tables = pd.read_html(html_wrapped)
    dfAll = tables[0]

    df = dfAll.copy(deep=True)

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

    return row["Supplier"], row[key], dfAll


# Load Pickle File
allFile = 'allData.pkl'
if not os.path.exists(allFile):
    firstPull = True
else:
    firstPull = False
    dfAll = pd.read_pickle(allFile)

file = "elec_gas_data.csv"

today = date.today()
formatted_time = datetime.now().strftime("%H:%M:%S")

data_list = []


for key in providers.elec:
    params = {
    "Category": "Electric",
    "TerritoryId": key,
    "RateCode": 1
    }

    supplier, price, dfProv = get_min_offer(params)

    new_data = {"Date": today, 
                "ElecOrGas": 'elec', 
                'TerritoryId': key, 
                'Rate':price, 
                'Supplier':supplier,
                'Time':formatted_time}
    data_list.append(new_data)

    if firstPull:
        dfAll = dfProv
        firstPull = False
    else:
        dfAll = pd.concat([dfAll, dfProv], ignore_index=True)
    

for key in providers.gas:
    params = {
    "Category": "Gas",
    "TerritoryId": key,
    "RateCode": 1
    }

    supplier, price, dfProv = get_min_offer(params)

    new_data = {"Date": today, 
                "ElecOrGas": 'gas', 
                'TerritoryId': key, 
                'Rate':price, 
                'Supplier':supplier,
                'Time':formatted_time}
    data_list.append(new_data)

    dfAll = pd.concat([dfAll, dfProv], ignore_index=True)


df = pd.DataFrame(data_list)
dfFile = pd.read_csv(file)
df = pd.concat([dfFile, df])


# Write min file for plotting
df.to_csv(file, index=False) 

# Write all data file
dfAll['Date'] = today
dfAll['Time'] = formatted_time 
dfAll.to_pickle('allData.pkl')


'''
if not os.path.exists(file):
    with open(file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date","ElectricPrice","ElectricSupplier","GasPrice","GasSupplier"])

with open(file, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([today, elec_price, elec_supplier, gas_price, gas_supplier])
'''
