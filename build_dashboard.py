import pandas as pd
import plotly.graph_objects as go

df = pd.read_csv("elec_gas_data.csv")

df["Date"] = pd.to_datetime(df["Date"])

df["Electric7"] = df["ElectricPrice"].rolling(7).mean()
df["Gas7"] = df["GasPrice"].rolling(7).mean()

fig = go.Figure()

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["ElectricPrice"],
name="Electric ($/kWh)",
mode="lines+markers"
)
)

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["GasPrice"],
name="Gas ($/Mcf)",
mode="lines+markers"
)
)

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["Electric7"],
name="Electric 7-day avg",
line=dict(dash="dash")
)
)

fig.add_trace(
go.Scatter(
x=df["Date"],
y=df["Gas7"],
name="Gas 7-day avg",
line=dict(dash="dash")
)
)

fig.update_layout(
title="Ohio Energy Price Tracker",
xaxis_title="Date",
yaxis_title="Price",
template="plotly_white"
)

fig.write_html("index.html")
