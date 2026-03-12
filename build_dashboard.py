import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import providers

df = pd.read_csv("elec_gas_data.csv")

df["Date"] = pd.to_datetime(df["Date"])

fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=("Electric Rate", "Gas Rate"))

dfEner = df[df['ElecOrGas']=='elec']
for key in providers.elec:
    dfTerr = dfEner[dfEner['TerritoryId']==key]
    fig.add_trace(
    go.Scatter(
    x=dfTerr["Date"],
    y=dfTerr["Rate"],
    name=providers.elec[key],
    mode="lines+markers",
    showlegend=True,
    legendgroup = '1'
    ), row=1, col=1
    )

dfEner = df[df['ElecOrGas']=='gas']
for key in providers.gas:
    dfTerr = dfEner[dfEner['TerritoryId']==key]
    fig.add_trace(
    go.Scatter(
    x=dfTerr["Date"],
    y=dfTerr["Rate"],
    name=providers.gas[key],
    mode="lines+markers",
    showlegend=True,
    legendgroup = '2'
    ), row=2, col=1
    )

fig.update_layout(title_text="Ohio Energy Choice Minimum Rate: Fixed, 6 months Term or Longer, No Fees",
                  legend_tracegroupgap=400)

fig.update_yaxes(title_text="$/kWh", row=1, col=1)
fig.update_yaxes(title_text="$/Ccl", row=2, col=1)
fig.update_xaxes(tickformat="%m/%d/%Y",dtick=86400000)

fig.write_html("index.html")