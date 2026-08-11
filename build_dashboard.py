import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime

# 1. Import utility names from your providers.py file
try:
    from providers import elec, gas
except ImportError:
    elec = {9:'AES Power', 2:'AEP', 4:'Duke', 7:'Ohio Edison', 6:'Ilumminating Co', 3:'Toledo Edison'}
    gas = {1:'Enbridge-Dominion', 11:'Centerpoint', 10:'Duke', 8:'Columbia'}

def fig_to_html_no_bdata(fig):
    import json
    import base64
    import uuid
    import numpy as np

    fig_dict = fig.to_dict()

    def decode_plotly_bdata(obj):
        import numpy as np
        if isinstance(obj, dict):
            if 'bdata' in obj and 'dtype' in obj:
                dtype_map = {'f8': '<f8', 'f4': '<f4', 'i4': '<i4', 'i8': '<i8'}
                dt = dtype_map.get(obj['dtype'], obj['dtype'])
                binary = base64.b64decode(obj['bdata'])
                arr = np.frombuffer(binary, dtype=dt)
                return arr.tolist()
            return {k: decode_plotly_bdata(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decode_plotly_bdata(x) for x in obj]
        elif isinstance(obj, tuple):
            return [decode_plotly_bdata(x) for x in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.int64, np.int32)):
            return int(obj)
        else:
            return obj

    fig_dict_decoded = decode_plotly_bdata(fig_dict)
    
    div_id = f"plotly-graph-{uuid.uuid4()}"
    data_json = json.dumps(fig_dict_decoded.get('data', []))
    layout_json = json.dumps(fig_dict_decoded.get('layout', {}))
    
    config = fig_dict_decoded.get('config', {})
    config['responsive'] = True
    config_json = json.dumps(config)

    html = f"""
    <div id="{div_id}" class="plotly-graph-div" style="height:100%; width:100%;"></div>
    <script type="text/javascript">
        (function() {{
            const gd = document.getElementById('{div_id}');
            Plotly.newPlot(gd, {data_json}, {layout_json}, {config_json});
        }})();
    </script>
    """
    return html

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
    
    # Ensure numeric types for proper sorting and comparison
    filtered_df['rate'] = pd.to_numeric(filtered_df['rate'], errors='coerce')
    filtered_df['Term. Length'] = pd.to_numeric(filtered_df['Term. Length'], errors='coerce')

    # --- 3. TIMEZONE CONVERSION (EST/EDT) ---
    filtered_df['Date'] = pd.to_datetime(filtered_df['Date'])
    if filtered_df['Date'].dt.tz is None:
        filtered_df['Date'] = filtered_df['Date'].dt.tz_localize('UTC')
    filtered_df['Date'] = filtered_df['Date'].dt.tz_convert('US/Eastern')

    # --- 4. APPLY UTILITY NAMES ---
    if elecHtml:
        filtered_df['Utility'] = filtered_df['Provider'].map(elec)
    else:
        filtered_df['Utility'] = filtered_df['Provider'].map(gas)
    
    filtered_df['Utility'] = filtered_df['Utility'].fillna(filtered_df['Supplier'].str.split().str[0])

    # --- 5. GENERATE HISTORICAL GRAPHS ---
    # Normalize Date to daily resolution to prevent vertical lines from multiple scrapes on the same day
    filtered_df['Date_Day'] = filtered_df['Date'].dt.normalize()
    min_rates_hist = filtered_df.groupby(['Utility', 'Term. Length', 'Date_Day'])['rate'].min().reset_index()
    min_rates_hist = min_rates_hist.rename(columns={'Date_Day': 'Date'})
    
    # Only show 6, 9, 12, 18, 24, 30, 36 months data in historical trends
    allowed_terms = [6, 9, 12, 18, 24, 30, 36]
    min_rates_hist = min_rates_hist[min_rates_hist['Term. Length'].isin(allowed_terms)].copy()

    # Reindex to insert NaNs for any missing dates (gaps in data)
    if not min_rates_hist.empty:
        all_dates = pd.date_range(
            start=min_rates_hist['Date'].min(),
            end=min_rates_hist['Date'].max(),
            freq='D'
        )
        utilities = min_rates_hist['Utility'].unique()
        terms = min_rates_hist['Term. Length'].unique()
        
        idx = pd.MultiIndex.from_product(
            [utilities, terms, all_dates],
            names=['Utility', 'Term. Length', 'Date']
        )
        min_rates_hist = min_rates_hist.set_index(['Utility', 'Term. Length', 'Date']).reindex(idx).reset_index()

    # Sort values and convert Date to clean string date representation for Plotly JS
    min_rates_hist = min_rates_hist.sort_values(by=['Utility', 'Term. Length', 'Date'])
    min_rates_hist['Date'] = min_rates_hist['Date'].dt.strftime('%Y-%m-%d')

    y_min, y_max = min_rates_hist['rate'].min(), min_rates_hist['rate'].max()
    y_padding = (y_max - y_min) * 0.05
    y_range = [y_min - y_padding, y_max + y_padding]

    min_rates_hist['Term_Str'] = min_rates_hist['Term. Length'].astype(str) + " Mo"
    term_order_desc = sorted(min_rates_hist['Term_Str'].dropna().unique(), key=lambda x: float(x.split()[0]), reverse=True)

    # Generate Jet Color Scale Map proportional to the length of the term
    def get_jet_color(val):
        colors = [
            (0, 120, 255),    # Vibrant Blue
            (0, 240, 255),    # Cyan
            (0, 255, 100),    # Bright Green
            (255, 255, 0),    # Yellow
            (255, 130, 0),    # Orange
            (255, 40, 40)     # Bright Red
        ]
        N = len(colors)
        scaled_val = val * (N - 1)
        idx1 = int(scaled_val)
        idx2 = min(idx1 + 1, N - 1)
        factor = scaled_val - idx1
        r1, g1, b1 = colors[idx1]
        r2, g2, b2 = colors[idx2]
        r = int(r1 + (r2 - r1) * factor)
        g = int(g1 + (g2 - g1) * factor)
        b = int(b1 + (b2 - b1) * factor)
        return f"rgb({r},{g},{b})"

    color_discrete_map = {}
    for term in allowed_terms:
        val = (term - min(allowed_terms)) / (max(allowed_terms) - min(allowed_terms))
        color_discrete_map[f"{float(term)} Mo"] = get_jet_color(val)

    num_utilities = len(min_rates_hist['Utility'].dropna().unique())
    dynamic_height = 450 * num_utilities
    row_spacing = min(0.02, 0.8 / (num_utilities - 1)) if num_utilities > 1 else 0.07

    unit = "$/kWh" if elecHtml else "$/MCF"
    
    # 1. Generate the main faceted chart (All Utilities)
    fig_all = px.line(
        min_rates_hist, x='Date', y='rate', color='Term_Str', symbol='Term_Str',
        facet_col='Utility', facet_col_wrap=1,
        facet_row_spacing=row_spacing,
        title=f'Historical Rate Trends ({unit}) - All Utilities',
        labels={'rate': f'Rate ({unit})', 'Term_Str': 'Term', 'Utility': 'Utility'},
        markers=True, category_orders={"Term_Str": term_order_desc},
        color_discrete_map=color_discrete_map
    )
    fig_all.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>"))
    fig_all.update_xaxes(type='date', tickformat="%Y-%m-%d", matches='x')
    fig_all.update_yaxes(range=y_range, matches='y')
    fig_all.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        legend_title_text='Plan Term',
        hovermode='x unified',
        height=dynamic_height,
        margin=dict(t=100, b=50)
    )
    graph_all_html = fig_to_html_no_bdata(fig_all)

    # 2. Generate individual utility charts and construct dropdown list
    utilities = sorted(min_rates_hist['Utility'].dropna().unique())
    select_options = ['<option value="all">All Providers</option>']
    graphs_html_list = [f'<div id="graph-all" class="graph-container" data-provider="all">{graph_all_html}</div>']

    for util in utilities:
        safe_util_id = "".join([c if c.isalnum() else "_" for c in util])
        select_options.append(f'<option value="{safe_util_id}">{util}</option>')

        util_df = min_rates_hist[min_rates_hist['Utility'] == util]
        if util_df.dropna(subset=['rate']).empty:
            continue

        fig_util = px.line(
            util_df, x='Date', y='rate', color='Term_Str', symbol='Term_Str',
            title=f'Historical Rate Trends ({unit}) - {util}',
            labels={'rate': f'Rate ({unit})', 'Term_Str': 'Term'},
            markers=True, category_orders={"Term_Str": term_order_desc},
            color_discrete_map=color_discrete_map
        )
        fig_util.update_xaxes(type='date', tickformat="%Y-%m-%d")
        fig_util.update_yaxes(range=y_range)
        fig_util.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend_title_text='Plan Term',
            hovermode='x unified',
            height=500,
            margin=dict(t=80, b=50)
        )
        util_graph_html = fig_to_html_no_bdata(fig_util)
        graphs_html_list.append(f'<div id="graph-{safe_util_id}" class="graph-container" data-provider="{safe_util_id}" style="display: none;">{util_graph_html}</div>')

    select_html = "".join(select_options)
    graphs_html = "".join(graphs_html_list)

    # --- 6. GENERATE TABLES (Strict "Todays Data" Only) ---
    today_df = filtered_df[filtered_df['Todays Data'] == True].copy()
    
    table_sections = []
    if not today_df.empty:
        today_min = today_df.loc[today_df.groupby(['Utility', 'Term. Length'])['rate'].idxmin()]

        for util in utilities:
            u_data = today_min[today_min['Utility'] == util].sort_values(['Term. Length', 'rate'])
            if u_data.empty:
                continue
            best_overall_rate = u_data['rate'].min()

            safe_util_id = "".join([c if c.isalnum() else "_" for c in util])
            section = f'<div class="provider-section" data-provider="{safe_util_id}">'
            section += f"<h2>{util}</h2>"
            section += f"<table><thead><tr><th>Supplier Entity</th><th>Term</th><th>Rate ({unit})</th></tr></thead><tbody>"

            for _, row in u_data.iterrows():
                is_best_val = (row['rate'] == best_overall_rate)
                is_below_thresh = threshold_rate is not None and row['rate'] < threshold_rate
                
                rate_display = f"{row['rate']:.5f}"
                if is_best_val:
                    rate_html = f'<span class="badge badge-best">★ {rate_display}</span>'
                elif is_below_thresh:
                    rate_html = f'<span class="badge badge-thresh">↓ {rate_display}</span>'
                else:
                    rate_html = f'<span class="rate-cell">{rate_display}</span>'
                
                section += f"<tr><td>{row['Supplier']}</td><td>{row['Term. Length']} Mo</td><td>{rate_html}</td></tr>"
            section += "</tbody></table></div>"
            table_sections.append(section)
    else:
        table_sections = ['<div class="provider-section" data-provider="all"><p style="text-align:center; color:#ef4444; font-weight:600; margin:0;">No new data has been updated for today yet.</p></div>']

    # --- 7. ASSEMBLE FINAL HTML ---
    dashboard_title = "Electric Dashboard" if elecHtml else "Gas Dashboard"
    
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{dashboard_title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        :root {{
            --bg-primary: #0b0f19;
            --bg-card: #111827;
            --bg-hover: #1f2937;
            --border-color: #1f2937;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent: #4f46e5;
            --accent-glow: rgba(79, 70, 229, 0.15);
        }}

        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            margin: 0;
            padding: 40px 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: auto;
        }}

        .header-nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
        }}

        .nav-link {{
            display: inline-block;
            text-align: center;
            font-weight: 600;
            font-size: 0.9em;
            color: #818cf8;
            text-decoration: none;
            border: 1px solid #312e81;
            background: rgba(49, 46, 129, 0.2);
            padding: 10px 20px;
            border-radius: 8px;
            transition: all 0.2s ease;
        }}

        .nav-link:hover {{
            background-color: #4f46e5;
            color: white;
            border-color: #4f46e5;
            box-shadow: 0 0 15px rgba(79, 70, 229, 0.4);
        }}

        h1.dashboard-header {{
            font-size: 2.2em;
            font-weight: 800;
            background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            letter-spacing: -0.025em;
        }}

        .control-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 32px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            align-items: flex-start;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        }}

        @media (min-width: 600px) {{
            .control-card {{
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
            }}
        }}

        .control-card label {{
            font-size: 1.1em;
            font-weight: 600;
            color: #e5e7eb;
        }}

        .control-card select {{
            background: #1f2937;
            border: 1px solid #374151;
            color: #f3f4f6;
            padding: 12px 24px;
            border-radius: 10px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            outline: none;
            transition: all 0.2s ease;
            width: 100%;
            max-width: 320px;
        }}

        .control-card select:hover {{
            border-color: #4f46e5;
            background: #283548;
        }}

        .control-card select:focus {{
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.3);
        }}

        .section-header {{
            font-size: 1.5em;
            font-weight: 700;
            color: #f3f4f6;
            margin-top: 40px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .section-header::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: var(--border-color);
        }}

        .provider-section {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            transition: transform 0.25s ease, box-shadow 0.25s ease, opacity 0.3s ease;
        }}

        .provider-section:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 20px -3px rgba(0, 0, 0, 0.4);
            border-color: #2e3b52;
        }}

        .provider-section h2 {{
            color: #a5b4fc;
            margin-top: 0;
            margin-bottom: 20px;
            font-size: 1.25em;
            font-weight: 700;
            letter-spacing: -0.01em;
        }}

        table {{
            border-collapse: collapse;
            width: 100%;
            border-radius: 10px;
            overflow: hidden;
        }}

        th, td {{
            padding: 14px 20px;
            text-align: left;
        }}

        th {{
            background-color: #1f2937;
            color: #9ca3af;
            text-transform: uppercase;
            font-size: 0.75em;
            font-weight: 700;
            letter-spacing: 0.05em;
            border-bottom: 2px solid #374151;
        }}

        td {{
            border-bottom: 1px solid #1f2937;
            color: #d1d5db;
            font-size: 0.95em;
        }}

        tr:last-child td {{
            border-bottom: none;
        }}

        tr:hover td {{
            background-color: rgba(31, 41, 55, 0.4);
            color: #ffffff;
        }}

        .rate-cell {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-weight: 600;
        }}

        .badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 700;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}

        .badge-best {{
            background-color: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
            box-shadow: 0 0 10px rgba(16, 185, 129, 0.1);
        }}

        .badge-thresh {{
            background-color: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.1);
        }}

        .graph-container {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }}

        .section-divider {{
            margin-top: 48px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-nav">
            <h1 class="dashboard-header">{dashboard_title}</h1>
            <a href="{top_link_url}" class="nav-link">{top_link_text}</a>
        </div>
        
        <div class="control-card">
            <label for="provider-select">Filter by Provider:</label>
            <select id="provider-select" onchange="filterProvider()">
                {select_html}
            </select>
        </div>

        <div class="graph-section">
            <div class="section-header">Historical Trends</div>
            {graphs_html}
        </div>

        <div class="table-section section-divider">
            <div class="section-header">Current Market Leaderboard</div>
            {"".join(table_sections)}
        </div>
    </div>

    <script>
        function filterProvider() {{
            const select = document.getElementById('provider-select');
            const selected = select.value;
            
            // 1. Filter table sections
            const sections = document.querySelectorAll('.provider-section');
            sections.forEach(sec => {{
                const prov = sec.getAttribute('data-provider');
                if (selected === 'all' || prov === selected) {{
                    sec.style.display = 'block';
                    sec.style.opacity = '0';
                    setTimeout(() => {{
                        sec.style.transition = 'opacity 0.3s ease';
                        sec.style.opacity = '1';
                    }}, 10);
                }} else {{
                    sec.style.display = 'none';
                }}
            }});
            
            // 2. Filter graph containers
            const graphs = document.querySelectorAll('.graph-container');
            graphs.forEach(g => {{
                const prov = g.getAttribute('data-provider');
                if (prov === selected) {{
                    g.style.display = 'block';
                    
                    // Trigger Plotly resize to draw graph properly in newly shown container
                    const gd = g.querySelector('.plotly-graph-div');
                    if (gd) {{
                        Plotly.Plots.resize(gd);
                    }}
                }} else {{
                    g.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>"""
    
    with open(html_file_name, 'w', encoding='utf-8') as f:
        f.write(full_html)


# --- EXECUTION ---
data_file = 'allData.parquet'

generate_energy_dashboard(
    file_path=data_file, 
    html_file_name='electric_dashboard.html', 
    elecHtml=True, 
    top_link_url="gas_dashboard.html", 
    top_link_text="Switch to Gas Dashboard", 
    threshold_rate=0.0869
)

generate_energy_dashboard(
    file_path=data_file, 
    html_file_name='gas_dashboard.html', 
    elecHtml=False, 
    top_link_url="electric_dashboard.html", 
    top_link_text="Switch to Electric Dashboard", 
    threshold_rate=2.99
)
