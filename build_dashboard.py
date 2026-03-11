import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

df = pd.read_csv("elec_gas_data.csv")

df["Date"] = pd.to_datetime(df["Date"])

#df["Electric7"] = df["ElectricPrice"].rolling(7).mean()
#df["Gas7"] = df["GasPrice"].rolling(7).mean()


fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=("Electric Rate", "Gas Rate"))


#fig = go.Figure()
'''
        fig.add_trace(go.Scatterpolar(
            r=currentPolar["BTV"], theta=currentPolar["AWA"], mode='markers+lines', line=dict(color=color, width=2, shape='spline'),
            name=f"{tw} kts TWS", legendgroup=f"tws{tw}", showlegend=False
        ), row=1, col=1)
'''

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["ElecPrice"],
name="Electric ($/kWh)",
mode="lines+markers",
showlegend=False
), row=1, col=1
)

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["GasPrice"],
name="Gas ($/Mcf)",
mode="lines+markers",
showlegend=False
), row=2, col=1
)




''''
fig.update_layout(
title="Ohio Energy Price Tracker",
xaxis_title="Date",
yaxis_title="Price",
template="plotly_white"
)
'''

fig.write_html("index.html")
