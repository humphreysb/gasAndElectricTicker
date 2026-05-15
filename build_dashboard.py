import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime
import json

# 1. Import utility names from your providers.py file
try:
    from providers import elec, gas
except ImportError:
    elec = {9:'AES Power', 2:'AEP', 4:'Duke', 7:'Ohio Edison', 6:'Ilumminating Co', 3:'Toledo Edison'}
    gas = {1:'Enbridge-Dominion', 11:'Centerpoint', 10:'Duke', 8:'Columbia'}

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
    min_rates_hist = filtered_df.groupby(['Utility', 'Term. Length', 'Date'])['rate'].min().reset_index()
    min_rates_hist = min_rates_hist.sort_values(by=['Utility', 'Term. Length', 'Date'])

    y_min, y_max = min_rates_hist['rate'].min(), min_rates_hist['rate'].max()
    y_padding = (y_max - y_min) * 0.05
    y_range = [y_min - y_padding, y_max + y_padding]

    min_rates_hist['Term_Str'] = min_rates_hist['Term. Length'].astype(str) + " Mo"
    term_order_desc = sorted(min_rates_hist['Term_Str'].unique(), key=lambda x: float(x.split()[0]), reverse=True)

    num_utilities = len(min_rates_hist['Utility'].unique())
    dynamic_height = 450 * num_utilities

    unit = "$/kWh" if elecHtml else "$/MCF"
    fig = px.line(
        min_rates_hist, x='Date', y='rate', color='Term_Str', symbol='Term_Str',
        facet_col='Utility', facet_col_wrap=1,
        title=f'Historical Rate Trends ({unit})',
        labels={'rate': f'Rate ({unit})', 'Term_Str': 'Term', 'Utility': 'Utility'},
        markers=True, category_orders={"Term_Str": term_order_desc}
    )

    fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>"))
    fig.update_xaxes(tickformat="%Y-%m-%d", matches='x')
    fig.update_yaxes(range=y_range, matches='y')
    fig.update_layout(legend_title_text='Plan Term', hovermode='x unified', height=dynamic_height, margin=dict(t=100, b=50))
    
    graph_html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

    # --- 6. GENERATE TABLES (Strict "Todays Data" Only) ---
    # Filter only for rows marked as today's data
    today_df = filtered_df[filtered_df['Todays Data'] == True].copy()

    # 90-day low + savings calculator data
    latest_ts = filtered_df['Date'].max()
    window_start = latest_ts - pd.Timedelta(days=90)
    window_df = filtered_df[filtered_df['Date'] >= window_start]
    min_90d_by_util = {k: float(v) for k, v in window_df.groupby('Utility')['rate'].min().items()}

    # "Current" snapshot: prefer the Todays Data flag; fall back to most recent calendar date.
    if not today_df.empty:
        current_df = today_df
        current_date_str = today_df['Date'].max().strftime('%Y-%m-%d')
    else:
        latest_date = filtered_df['Date'].dt.normalize().max()
        current_df = filtered_df[filtered_df['Date'].dt.normalize() == latest_date]
        current_date_str = latest_date.strftime('%Y-%m-%d')

    current_min_by_util = {k: float(v) for k, v in current_df.groupby('Utility')['rate'].min().items()}

    is_90d_low_by_util = {
        u: abs(current_min_by_util[u] - min_90d_by_util.get(u, float('inf'))) < 1e-9
        for u in current_min_by_util
    }

    table_sections = []
    if not today_df.empty:
        # Get the best supplier per Utility and Term Length
        today_min = today_df.loc[today_df.groupby(['Utility', 'Term. Length'])['rate'].idxmin()]
        utilities = sorted(today_min['Utility'].unique())

        for util in utilities:
            u_data = today_min[today_min['Utility'] == util].sort_values(['Term. Length', 'rate'])
            best_overall_rate = u_data['rate'].min()

            badge_html = '<span class="badge-90d-low" title="Today\'s minimum matches the lowest rate in the last 90 days">90-DAY LOW</span>' if is_90d_low_by_util.get(util, False) else ''
            section = f"<h2>{util} {badge_html}</h2>"
            section += f"<table><thead><tr><th>Supplier Entity</th><th>Term</th><th>Rate ({unit})</th></tr></thead><tbody>"

            for _, row in u_data.iterrows():
                # Bold if it's the absolute best value for this utility
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
    else:
        table_sections = ["<p style='text-align:center; color:#e74c3c;'>No new data has been updated for today yet.</p>"]

    # --- 7. ASSEMBLE FINAL HTML ---
    dashboard_title = "Electric Dashboard" if elecHtml else "Gas Dashboard"

    # --- Savings calculator data + UI ---
    usage_unit_label = "kWh" if elecHtml else "MCF"
    placeholder_rate = "0.10" if elecHtml else "5.00"
    placeholder_usage = "900" if elecHtml else "10"

    calc_data = {
        'unit': unit,
        'usage_unit': usage_unit_label,
        'dashboard_type': 'electric' if elecHtml else 'gas',
        'min_by_util': current_min_by_util,
        'latest_date': current_date_str,
    }
    calc_data_json = json.dumps(calc_data)

    util_options = "\n".join(
        f'<option value="{u}">{u}</option>' for u in sorted(current_min_by_util.keys())
    )

    extra_styles = """
            .badge-90d-low { display: inline-block; background: #27ae60; color: white; padding: 4px 10px; font-size: 0.55em; border-radius: 12px; vertical-align: middle; margin-left: 12px; font-weight: bold; letter-spacing: 0.5px; }
            .calc-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            .calc-form label { display: flex; flex-direction: column; font-weight: 600; color: #555; font-size: 0.9em; }
            .calc-form input, .calc-form select { margin-top: 6px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 1em; font-family: inherit; }
            .calc-results { margin-top: 20px; padding: 20px 24px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            .calc-prompt { color: #999; text-align: center; font-style: italic; margin: 0; }
            .calc-win { color: #27ae60; font-size: 1.1em; margin: 0 0 8px; font-weight: 600; }
            .calc-neutral { color: #f39c12; font-size: 1.05em; margin: 0; }
            .calc-results ul { font-size: 1.15em; line-height: 1.8; margin: 0; padding-left: 24px; }
            @media (max-width: 600px) { .calc-form { grid-template-columns: 1fr; } }
"""

    calculator_html = f"""
            <div class="calculator-section section-divider">
                <h1>Should I Switch?</h1>
                <div class="calc-form">
                    <label>My utility
                        <select id="calc-utility">
                            <option value="">— pick one —</option>
                            {util_options}
                        </select>
                    </label>
                    <label>My current rate ({unit})
                        <input type="number" step="0.00001" id="calc-current-rate" placeholder="e.g. {placeholder_rate}">
                    </label>
                    <label>Monthly usage ({usage_unit_label})
                        <input type="number" step="1" id="calc-usage" placeholder="e.g. {placeholder_usage}">
                    </label>
                    <label>Early termination fee ($, optional)
                        <input type="number" step="1" id="calc-etf" value="0">
                    </label>
                </div>
                <div class="calc-results" id="calc-results">
                    <p class="calc-prompt">Enter your details above to see savings.</p>
                </div>
            </div>
"""

    calculator_js = (
        "<script>\n(function() {\n"
        "  var DATA = " + calc_data_json + ";\n"
        "  var STORAGE_PREFIX = 'gAndETicker_' + DATA.dashboard_type + '_';\n"
        "  var IDS = ['calc-utility', 'calc-current-rate', 'calc-usage', 'calc-etf'];\n"
        "  function $(id) { return document.getElementById(id); }\n"
        "  function loadInputs() {\n"
        "    IDS.forEach(function(id) {\n"
        "      var saved = localStorage.getItem(STORAGE_PREFIX + id);\n"
        "      if (saved !== null) $(id).value = saved;\n"
        "    });\n"
        "  }\n"
        "  function saveInputs() {\n"
        "    IDS.forEach(function(id) {\n"
        "      localStorage.setItem(STORAGE_PREFIX + id, $(id).value);\n"
        "    });\n"
        "  }\n"
        "  function fmtMoney(n) {\n"
        "    return '$' + n.toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');\n"
        "  }\n"
        "  function render() {\n"
        "    var util = $('calc-utility').value;\n"
        "    var myRate = parseFloat($('calc-current-rate').value);\n"
        "    var usage = parseFloat($('calc-usage').value);\n"
        "    var etf = parseFloat($('calc-etf').value) || 0;\n"
        "    var results = $('calc-results');\n"
        "    if (!util || isNaN(myRate) || isNaN(usage) || usage <= 0) {\n"
        "      results.innerHTML = '<p class=\"calc-prompt\">Enter your utility, current rate, and monthly usage to see savings.</p>';\n"
        "      return;\n"
        "    }\n"
        "    var minRate = DATA.min_by_util[util];\n"
        "    if (minRate === undefined) {\n"
        "      results.innerHTML = '<p class=\"calc-prompt\">No current rate data for ' + util + '.</p>';\n"
        "      return;\n"
        "    }\n"
        "    var monthlyDiff = (myRate - minRate) * usage;\n"
        "    var yearlyDiff = monthlyDiff * 12;\n"
        "    var html = '';\n"
        "    html += '<p style=\"margin:0 0 12px;color:#555;font-size:0.95em;\">Comparing your <b>' + myRate.toFixed(5) + ' ' + DATA.unit + '</b> rate against ' + util + ' current daily minimum of <b>' + minRate.toFixed(5) + ' ' + DATA.unit + '</b> (as of ' + DATA.latest_date + ').</p>';\n"
        "    if (monthlyDiff <= 0) {\n"
        "      html += '<p class=\"calc-neutral\">Your rate is already at or below the current minimum. No switch needed.</p>';\n"
        "    } else {\n"
        "      html += '<p class=\"calc-win\">Switching could save you:</p><ul>';\n"
        "      html += '<li>' + fmtMoney(monthlyDiff) + ' / month</li>';\n"
        "      html += '<li>' + fmtMoney(yearlyDiff) + ' / year</li>';\n"
        "      if (etf > 0) {\n"
        "        var be = Math.ceil(etf / monthlyDiff);\n"
        "        html += '<li>Breakeven on ' + fmtMoney(etf) + ' early-termination fee: <b>' + be + ' month' + (be === 1 ? '' : 's') + '</b></li>';\n"
        "      }\n"
        "      html += '</ul>';\n"
        "    }\n"
        "    results.innerHTML = html;\n"
        "    saveInputs();\n"
        "  }\n"
        "  document.addEventListener('DOMContentLoaded', function() {\n"
        "    loadInputs();\n"
        "    IDS.forEach(function(id) {\n"
        "      var el = $(id);\n"
        "      el.addEventListener('input', render);\n"
        "      el.addEventListener('change', render);\n"
        "    });\n"
        "    render();\n"
        "  });\n"
        "})();\n</script>"
    )

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
            .section-divider {{ margin-top: 60px; padding-top: 20px; border-top: 3px double #ddd; }}{extra_styles}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="{top_link_url}" class="nav-link">{top_link_text}</a>
            <h1>{dashboard_title}</h1>

            <div class="table-section">
                <h1>Current Market Leaderboard</h1>
                {"".join(table_sections)}
            </div>
{calculator_html}
            <div class="graph-section section-divider">
                <h1>Historical Trends</h1>
                {graph_html}
            </div>
        </div>
        {calculator_js}
    </body>
    </html>
    """
    
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
