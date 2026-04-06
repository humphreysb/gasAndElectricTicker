import pandas as pd

df = pd.read_csv("allData.csv")

df.to_parquet('allData.parquet')

