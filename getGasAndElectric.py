import requests
import pandas as pd
import urllib3
from datetime import date
import csv

# disable SSL verification warning (your environment needs this)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

loadFromWeb = True


def getMinCost(loadFromWeb, params):
    if loadFromWeb:

        url = "https://energychoice.ohio.gov/ApplesToApplesComparision.aspx"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            params=params,
            headers=headers,
            verify=False
        )

        response.raise_for_status()
        # pandas automatically extracts tables
        tables = pd.read_html(response.text)
        # Apples-to-Apples offers table is the first table
        df = tables[0]

    else:  #data file
        df = pd.read_pickle("example_elec_data.pkl")

    # clean column names
    df.columns = df.columns.str.strip()

    #print(df.head())
    #print(df.columns)

    # Filter
    df = df[df['Rate Type'].str.contains('Fixed', case=False)]
    df = df[df['intro. price'].str.contains('No', case=False)]
    df['Term. Length'] = df['Term. Length'].str.extract(r'(\d+)')
    df['Term. Length'] = pd.to_numeric(df['Term. Length'])
    df = df[df['Term. Length'] >= 6]
    df = df[df['Early Term. Fee'].str.contains('\\$0', case=False, regex=True)]
    df = df[df['Monthly Fee'].str.contains('\\$0', case=False, regex=True)]
    df = df[df['promo. offers'].str.contains('No', case=False)]


    if params['Category'] == 'Electric':
        keyname = '$/kWh'
    else:
        keyname = '$/Mcf'

    df[keyname] = pd.to_numeric(df[keyname])
    minCost = df[keyname].to_numpy().min()

    return minCost






today = date.today()

params = {
    "Category": "Electric",
    "TerritoryId": 6,
    "RateCode": 1
}
minElecCost = getMinCost(loadFromWeb, params)

params = {
    "Category": "NaturalGas",
    "TerritoryId": 1,
    "RateCode": 1
}
minGasCost = getMinCost(loadFromWeb, params)







if False:     # Make a new file with header
    # Define the field names (column headers)
    fieldnames = ['Date', 'Electricity', 'Gas']

    output_file_path = 'elec_gas_data.csv'
    with open(output_file_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        # Write the header row
        writer.writeheader()



new_row_data = [today, minElecCost , minGasCost ]
with open('elec_gas_data.csv', mode='a', newline='') as file:
    csv_writer = csv.writer(file)   # Create a CSV writer object
    csv_writer.writerow(new_row_data)  # Append the new row to the CSV file

