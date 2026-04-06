import pandas as pd
import plotly.express as px
import plotly.io as pio


# 1. Import utility names from your providers.py file
from providers import elec
from providers import gas

def generate_energy_dashboard(file_path, html_file_name, elecHtml, top_link_url, top_link_text, threshold_rate):
    # --- 2. LOAD & INITIAL FILTERING ---
    df = pd.read_parquet(file_path)

    base_mask = (
        (df['electric'] == elecHtml) &
        (df['Fixed Rate'] == True) &
        (df['intro. price'] == False) &
        (df['Term. Length'] >= 6) &
        (df['Early Term. Fee'] == 0) &
        (df['Monthly Fee'] == 0)
    )
    filtered_df = df[base_mask].copy()
    filtered_df['Term. Length'] = pd.to_numeric(filtered_df['Term. Length'])

    # --- 3. APPLY UTILITY NAMES FROM providers.py ---
    if elecHtml:
        filtered_df['Utility'] = filtered_df['Provider'].map(elec)
    else:
        filtered_df['Utility'] = filtered_df['Provider'].map(gas)
    
    filtered_df['Utility'] = filtered_df['Utility'].fillna(filtered_df['Supplier'].str.split().str[0])

    # --- 4. GENERATE HISTORICAL GRAPHS ---
    min_rates_hist = filtered_df.groupby(['Utility', 'Term. Length', 'Date'])['rate'].min().reset_index()
    min_rates_hist = min_rates_hist.sort_values(by=['Utility', 'Term. Length', 'Date'])

    # Sync Y-axis limits
    y_min, y_max = min_rates_hist['rate'].min(), min_rates_hist['rate'].max()
    y_padding = (y_max - y_min) * 0.05
    y_range = [y_min - y_padding, y_max + y_padding]

    # Sort legend High to Low
    min_rates_hist['Term_Str'] = min_rates_hist['Term. Length'].astype(str) + " Mo"
    term_order_desc = sorted(min_rates_hist['Term_Str'].unique(), key=lambda x: float(x.split()[0]), reverse=True)

    # Calculate plot height for vertical stack (approx 450px per chart)
    num_utilities = len(min_rates_hist['Utility'].unique())
    dynamic_height = 450 * num_utilities

    unit = "$/kWh" if elecHtml else "$/MCF"
    title_text = f'Historical Rate Trends ({unit})'

    fig = px.line(
        min_rates_hist, x='Date', y='rate', color='Term_Str', symbol='Term_Str',
        facet_col='Utility', 
        facet_col_wrap=1,  # Single column stack
        title=title_text,
        labels={'rate': f'Rate ({unit})', 'Term_Str': 'Term', 'Utility': 'Utility'},
        markers=True, 
        category_orders={"Term_Str": term_order_desc}
    )

    # Clean Subplot Titles (Remove "Utility=")
    fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>"))
    
    # Clean X-Axis (Date only)
    fig.update_xaxes(tickformat="%Y-%m-%d", matches='x')
    fig.update_yaxes(range=y_range, matches='y')
    
    # Final Layout - Standard Global Legend
    fig.update_layout(
        legend_title_text='Plan Term', 
        hovermode='x unified', 
        height=dynamic_height,
        margin=dict(t=100, b=50)
    )
    
    graph_html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

    # --- 5. GENERATE TABLES (Leaderboard) ---
    today_df = filtered_df[filtered_df['Todays Data'] == True].copy()
    today_min = today_df.loc[today_df.groupby(['Utility', 'Term. Length'])['rate'].idxmin()]
    
    table_sections = []
    utilities = sorted(today_min['Utility'].unique())

    for util in utilities:
        u_data = today_min[today_min['Utility'] == util].sort_values(['Term. Length', 'rate'])
        best_overall_rate = u_data['rate'].min()

        section = f"<h2>{util}</h2><table><thead><tr><th>Supplier Entity</th><th>Term</th><th>Rate ({unit})</th></tr></thead><tbody>"

        for _, row in u_data.iterrows():
            is_best_val = (row['rate'] == best_overall_rate)
            is_below_thresh = threshold_rate is not None and row['rate'] < threshold_rate
            
            cell_class = "min-rate" if is_best_val else ""
            if is_below_thresh: cell_class += " threshold-met"
            
            rate_display = f"{row['rate']:.5f}"
            if is_best_val: rate_display = f"<b>{rate_display}</b>"
            if is_below_thresh: rate_display = f"<i>{rate_display}</i>"
            
            section += f"<tr><td>{row['Supplier']}</td><td>{row['Term. Length']} Mo</td><td class='{cell_class}'>{rate_display}</td></tr>"
        section += "</tbody></table>"
        table_sections.append(section)

    # --- 6. ASSEMBLE FINAL HTML (Table TOP, Charts BOTTOM) ---
    dashboard_title = "Electric Dashboard" if elecHtml else "Gas Dashboard"
    
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{dashboard_title}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 40px; background-color: #fcfcfc; color: #333; }}
            .nav-link {{ display: block; text-align: center; font-weight: bold; margin-bottom: 30px; font-size: 1.3em; color: #2980b9; text-decoration: none; border: 2px solid #2980b9; padding: 10px; border-radius: 5px; width: fit-content; margin: auto; }}
            .nav-link:hover {{ background-color: #2980b9; color: white; }}
            h1 {{ text-align: center; color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            h2 {{ color: #2980b9; margin-top: 50px; border-left: 10px solid #2980b9; padding-left: 15px; background: #f1f7fa; padding: 8px 15px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f8f9fa; color: #555; text-transform: uppercase; font-size: 0.85em; }}
            .min-rate {{ background-color: #f0fff4; color: #27ae60; }}
            .threshold-met {{ font-style: italic; text-decoration: underline; }}
            .container {{ max-width: 1100px; margin: auto; }}
            .section-divider {{ margin-top: 60px; padding-top: 20px; border-top: 3px double #ddd; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="{top_link_url}" class="nav-link" target="_blank">{top_link_text}</a>
            <h1>{dashboard_title}</h1>
            
            <div class="table-section">
                <h1>Current Market Leaderboard (Today's Data)</h1>
                {"".join(table_sections)}
            </div>

            <div class="graph-section section-divider">
                <h1>Historical Trends</h1>
                {graph_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    with open(html_file_name, 'w', encoding='utf-8') as f:
        f.write(full_html)

# --- EXECUTION ---
# Electric Dashboard
generate_energy_dashboard(
    file_path='allData.parquet', 
    html_file_name='electric_dashboard.html', 
    elecHtml=True, 
    top_link_url="https://humphreysb.github.io/gasAndElectricTicker/gas_dashboard.html", 
    top_link_text="Switch to Gas Dashboard", 
    threshold_rate=0.0869
)

# Gas Dashboard
generate_energy_dashboard(
    file_path='allData.parquet', 
    html_file_name='gas_dashboard.html', 
    elecHtml=False, 
    top_link_url="https://humphreysb.github.io/gasAndElectricTicker/electric_dashboard.html", 
    top_link_text="Switch to Electric Dashboard", 
    threshold_rate=3.764
)