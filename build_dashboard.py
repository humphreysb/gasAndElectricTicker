import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    term_order_asc = sorted(min_rates_hist['Term_Str'].unique(), key=lambda x: float(x.split()[0]))

    unit = "$/kWh" if elecHtml else "$/MCF"
    num_utilities = len(min_rates_hist['Utility'].unique())
    num_terms = len(term_order_asc)

    PLOT_FONT = dict(family='-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color='#1a2233')

    def _style_chart(fig, height, show_legend=True):
        fig.update_xaxes(tickformat="%Y-%m-%d")
        fig.update_layout(
            hovermode='x unified', height=height,
            margin=dict(t=30, b=40, l=55, r=20),
            paper_bgcolor='white', plot_bgcolor='#fafbfc',
            font=PLOT_FONT,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0) if show_legend else dict(),
            showlegend=show_legend,
        )
        return fig

    # View 1: each utility (facet), all terms (color) — current default
    fig1 = px.line(
        min_rates_hist, x='Date', y='rate', color='Term_Str', symbol='Term_Str',
        facet_col='Utility', facet_col_wrap=1,
        labels={'rate': f'Rate ({unit})', 'Term_Str': 'Term'},
        markers=True, category_orders={"Term_Str": term_order_desc},
    )
    fig1.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", font=dict(size=13)))
    fig1.update_xaxes(matches='x')
    fig1.update_yaxes(range=y_range, matches='y')
    _style_chart(fig1, 240 * num_utilities + 80)
    fig1.update_layout(legend_title_text='Term')

    # View 2: each term (facet), all utilities (color)
    fig2 = px.line(
        min_rates_hist, x='Date', y='rate', color='Utility',
        facet_col='Term_Str', facet_col_wrap=1,
        labels={'rate': f'Rate ({unit})'},
        markers=True, category_orders={"Term_Str": term_order_asc},
    )
    fig2.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", font=dict(size=13)))
    fig2.update_xaxes(matches='x')
    fig2.update_yaxes(range=y_range, matches='y')
    _style_chart(fig2, 240 * num_terms + 80)
    fig2.update_layout(legend_title_text='Utility')

    # View 3: cheapest daily rate per utility (min across all terms)
    cheapest_per_util_day = (
        filtered_df.assign(Day=filtered_df['Date'].dt.normalize())
                   .groupby(['Utility', 'Day'])['rate'].min().reset_index()
                   .rename(columns={'Day': 'Date'})
                   .sort_values(['Utility', 'Date'])
    )
    fig3 = px.line(
        cheapest_per_util_day, x='Date', y='rate', color='Utility',
        labels={'rate': f'Best Rate ({unit})'},
        markers=True,
    )
    fig3.update_yaxes(range=y_range)
    _style_chart(fig3, 520)
    fig3.update_layout(legend_title_text='Utility')

    # View 4: market minimum — the lowest rate anywhere each day
    market_min_day = (
        filtered_df.assign(Day=filtered_df['Date'].dt.normalize())
                   .groupby('Day')['rate'].min().reset_index()
                   .rename(columns={'Day': 'Date'})
                   .sort_values('Date')
    )
    fig4 = px.line(
        market_min_day, x='Date', y='rate',
        labels={'rate': f'Market Min ({unit})'},
        markers=True,
    )
    fig4.update_traces(line=dict(color='#15803d', width=3), marker=dict(color='#15803d', size=7))
    fig4.update_yaxes(range=y_range)
    _style_chart(fig4, 420, show_legend=False)

    chart_views_meta = [
        ('by-utility', 'Each utility, all terms',                fig1),
        ('by-term',    'Each term, all utilities',               fig2),
        ('cheap-util', 'Cheapest rate per utility',              fig3),
        ('market-min', 'Market minimum (cheapest rate anywhere)', fig4),
    ]
    chart_html_parts = []
    for i, (vid, _label, fig) in enumerate(chart_views_meta):
        include_js = 'cdn' if i == 0 else False
        inner = pio.to_html(fig, full_html=False, include_plotlyjs=include_js)
        hidden_attr = '' if i == 0 else ' hidden'
        chart_html_parts.append(f'<div class="chart-view" data-view="{vid}"{hidden_attr}>{inner}</div>')
    chart_views_html = "".join(chart_html_parts)
    chart_view_options = "\n".join(
        f'<option value="{vid}">{label}</option>' for vid, label, _ in chart_views_meta
    )

    # --- 5b. LONG-TERM TREND VIEWS (weekly / monthly / yearly / seasonality) ---
    span_days = max((filtered_df['Date'].max() - filtered_df['Date'].min()).days + 1, 1)
    span_weeks = span_days / 7
    span_months = span_days / 30.4
    span_years = span_days / 365.25

    # Aggregations
    weekly_summary = (
        filtered_df.assign(Bucket=filtered_df['Date'].dt.tz_localize(None).dt.to_period('W').dt.start_time)
                   .groupby('Bucket')['rate'].agg(avg='mean', minimum='min').reset_index()
                   .rename(columns={'Bucket': 'Date'})
                   .sort_values('Date')
    )
    monthly_summary = (
        filtered_df.assign(Bucket=filtered_df['Date'].dt.tz_localize(None).dt.to_period('M').dt.start_time)
                   .groupby('Bucket')['rate'].agg(avg='mean', minimum='min').reset_index()
                   .rename(columns={'Bucket': 'Date'})
                   .sort_values('Date')
    )
    yearly_summary = (
        filtered_df.assign(Year=filtered_df['Date'].dt.year)
                   .groupby('Year')['rate'].agg(avg='mean', minimum='min').reset_index()
                   .sort_values('Year')
    )

    MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    season_actual = (
        filtered_df.assign(Month=filtered_df['Date'].dt.month)
                   .groupby('Month')['rate'].agg(avg='mean', minimum='min').reset_index()
    )
    # Pad to all 12 months so the chart always shows full year
    seasonality = pd.DataFrame({'Month': range(1, 13)}).merge(season_actual, on='Month', how='left')
    seasonality['MonthName'] = seasonality['Month'].map(lambda m: MONTH_NAMES[m - 1])
    season_observed = seasonality.dropna(subset=['avg'])
    lowest_idx = season_observed['avg'].idxmin() if not season_observed.empty else None
    lowest_month_num = int(seasonality.loc[lowest_idx, 'Month']) if lowest_idx is not None else None
    lowest_month_name = seasonality.loc[lowest_idx, 'MonthName'] if lowest_idx is not None else None
    lowest_month_avg = float(seasonality.loc[lowest_idx, 'avg']) if lowest_idx is not None else None

    def _trend_line(df_in, title_y, height):
        f = go.Figure()
        f.add_trace(go.Scatter(
            x=df_in['Date'], y=df_in['avg'], mode='lines+markers',
            name=f'Avg ({unit})',
            line=dict(color='#1a2233', width=2), marker=dict(size=7),
        ))
        f.add_trace(go.Scatter(
            x=df_in['Date'], y=df_in['minimum'], mode='lines+markers',
            name=f'Min ({unit})',
            line=dict(color='#15803d', width=2, dash='dot'), marker=dict(size=7),
        ))
        f.update_yaxes(title_text=title_y)
        return _style_chart(f, height)

    fig_weekly = _trend_line(weekly_summary, f'Rate ({unit})', 420)
    fig_monthly = _trend_line(monthly_summary, f'Rate ({unit})', 420)

    # Yearly: bar chart (small number of points)
    fig_yearly = go.Figure()
    fig_yearly.add_trace(go.Bar(
        x=yearly_summary['Year'].astype(str), y=yearly_summary['avg'],
        name=f'Avg ({unit})', marker=dict(color='#1a2233'),
    ))
    fig_yearly.add_trace(go.Bar(
        x=yearly_summary['Year'].astype(str), y=yearly_summary['minimum'],
        name=f'Min ({unit})', marker=dict(color='#15803d'),
    ))
    fig_yearly.update_yaxes(title_text=f'Rate ({unit})')
    fig_yearly.update_xaxes(title_text='Year')
    fig_yearly.update_layout(barmode='group')
    _style_chart(fig_yearly, 420)

    # Seasonality: bar chart of avg per calendar month, lowest highlighted
    bar_colors = []
    for _, r in seasonality.iterrows():
        if pd.isna(r['avg']):
            bar_colors.append('#e5e7eb')  # no data
        elif lowest_month_num is not None and int(r['Month']) == lowest_month_num:
            bar_colors.append('#15803d')  # lowest
        else:
            bar_colors.append('#9ca3af')  # observed

    fig_season = go.Figure()
    fig_season.add_trace(go.Bar(
        x=seasonality['MonthName'], y=seasonality['avg'],
        marker=dict(color=bar_colors),
        text=[f'{v:.4f}' if pd.notna(v) else 'no data' for v in seasonality['avg']],
        textposition='outside',
        hovertemplate='%{x}<br>Avg rate: %{y:.5f}<extra></extra>',
        name='Avg rate',
        showlegend=False,
    ))
    if lowest_month_name is not None and lowest_month_avg is not None:
        fig_season.add_annotation(
            x=lowest_month_name, y=lowest_month_avg,
            text=f'⬇ Lowest avg<br>({lowest_month_name})',
            showarrow=True, arrowhead=2, arrowcolor='#15803d',
            ax=0, ay=-40, font=dict(color='#15803d', size=12, family=PLOT_FONT['family']),
            bgcolor='white', bordercolor='#15803d', borderwidth=1, borderpad=4,
        )
    fig_season.update_yaxes(title_text=f'Avg rate ({unit})')
    fig_season.update_xaxes(title_text='Calendar month')
    _style_chart(fig_season, 460, show_legend=False)

    # Per-view sparsity notes
    def _note(needed_label, have_label, ok):
        cls = 'data-warning' if not ok else 'data-warning data-warning-ok'
        return f'<div class="{cls}">Have {have_label}. {needed_label}</div>'

    weekly_note = _note(
        'Need ~8+ weeks for a meaningful weekly trend.',
        f'{span_weeks:.1f} weeks of data',
        span_weeks >= 8,
    )
    monthly_note = _note(
        'Need ~6+ months for a meaningful monthly trend.',
        f'{span_months:.1f} months of data',
        span_months >= 6,
    )
    yearly_note = _note(
        'Need ≥2 years for a year-over-year view.',
        f'{span_years:.2f} years of data',
        span_years >= 2,
    )
    seasonality_note = _note(
        'Need ≥2 years (ideally 3+) before the "lowest month" marker is reliable.',
        f'{span_years:.2f} years of data covering {len(season_observed)} of 12 months',
        span_years >= 2,
    )

    trend_views_meta = [
        ('weekly',      'Weekly (avg + min)',                 fig_weekly,  weekly_note),
        ('monthly',     'Monthly (avg + min)',                fig_monthly, monthly_note),
        ('yearly',      'Yearly (avg + min)',                 fig_yearly,  yearly_note),
        ('seasonality', 'Seasonality — when are rates lowest?', fig_season,  seasonality_note),
    ]
    trend_html_parts = []
    for i, (vid, _label, fig, note) in enumerate(trend_views_meta):
        inner = pio.to_html(fig, full_html=False, include_plotlyjs=False)
        hidden_attr = '' if i == 0 else ' hidden'
        trend_html_parts.append(
            f'<div class="trend-view" data-trend="{vid}"{hidden_attr}>{note}{inner}</div>'
        )
    trend_views_html = "".join(trend_html_parts)
    trend_view_options = "\n".join(
        f'<option value="{vid}">{label}</option>' for vid, label, _, _ in trend_views_meta
    )

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
            current_min = current_min_by_util.get(util, best_overall_rate)

            badge_html = '<span class="badge-90d-low" title="Today\'s minimum matches the lowest rate in the last 90 days">90-DAY LOW</span>' if is_90d_low_by_util.get(util, False) else ''
            rate_pill = f'<span class="pill pill-rate">Min today: {current_min:.5f} {unit}</span>'

            section = '<article class="util-card">'
            section += f'<header class="util-card-head"><h3>{util}</h3>{rate_pill}{badge_html}</header>'
            section += f"<table><thead><tr><th>Supplier</th><th>Term</th><th>Rate ({unit})</th></tr></thead><tbody>"

            for _, row in u_data.iterrows():
                # Bold if it's the absolute best value for this utility
                is_best_val = (row['rate'] == best_overall_rate)
                is_below_thresh = threshold_rate is not None and row['rate'] < threshold_rate

                cell_class = "min-rate" if is_best_val else ""
                if is_below_thresh: cell_class += " threshold-met"

                rate_display = f"{row['rate']:.5f}"
                if is_best_val: rate_display = f"<b>{rate_display}</b>"

                section += f"<tr><td>{row['Supplier']}</td><td>{row['Term. Length']} Mo</td><td class='{cell_class}'>{rate_display}</td></tr>"
            section += "</tbody></table></article>"
            table_sections.append(section)
    else:
        table_sections = ['<p class="empty-state">No new data has been updated for today yet.</p>']

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

    styles_block = """
:root {
  --bg: #f6f7f9;
  --card: #ffffff;
  --text: #15202b;
  --muted: #677078;
  --border: #e4e7eb;
  --accent: #15803d;
  --accent-fade: #ecfdf5;
  --warn: #b45309;
  --warn-fade: #fffbeb;
  --shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.topnav {
  position: sticky; top: 0; z-index: 10;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: saturate(180%) blur(8px);
  -webkit-backdrop-filter: saturate(180%) blur(8px);
  border-bottom: 1px solid var(--border);
}
.topnav-inner {
  max-width: 1100px; margin: 0 auto;
  padding: 12px 24px;
  display: flex; align-items: center; gap: 16px;
}
.brand { font-weight: 700; font-size: 1.02em; color: var(--text); letter-spacing: -0.01em; }
.tabs { display: flex; gap: 4px; margin-left: auto; }
.tab {
  text-decoration: none; padding: 7px 14px; border-radius: 6px;
  color: var(--muted); font-weight: 600; font-size: 0.92em;
  transition: background 0.15s, color 0.15s;
}
.tab:hover { background: var(--bg); color: var(--text); }
.tab-active { background: var(--accent-fade); color: var(--accent); }
.container { max-width: 1100px; margin: 0 auto; padding: 28px 24px 64px; }
.page-header { margin-bottom: 24px; }
.page-header h1 {
  margin: 0 0 4px;
  font-size: 1.65em; font-weight: 700; letter-spacing: -0.015em;
  color: var(--text);
}
.subtitle { margin: 0; color: var(--muted); font-size: 0.92em; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 20px 24px;
  margin-bottom: 20px; box-shadow: var(--shadow);
}
.section-title {
  margin: 24px 0 12px;
  font-size: 0.74em; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.7px;
  color: var(--muted);
}
.section-title:first-child { margin-top: 0; }
.leaderboard-cards { display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; }
.util-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 20px; box-shadow: var(--shadow);
}
.util-card-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 6px; flex-wrap: wrap;
}
.util-card-head h3 { margin: 0; font-size: 1.02em; font-weight: 700; color: var(--text); }
.pill {
  display: inline-block; padding: 3px 10px;
  border-radius: 999px; font-size: 0.72em; font-weight: 600; letter-spacing: 0.2px;
}
.pill-rate { background: var(--bg); color: var(--muted); border: 1px solid var(--border); }
.badge-90d-low {
  background: var(--accent); color: white;
  padding: 3px 10px; border-radius: 999px;
  font-size: 0.68em; font-weight: 700; letter-spacing: 0.5px;
}
.util-card table { width: 100%; border-collapse: collapse; margin: 0; }
.util-card th, .util-card td {
  border: none; border-bottom: 1px solid var(--border);
  padding: 7px 4px; text-align: left; font-size: 0.92em;
}
.util-card tr:last-child td { border-bottom: none; }
.util-card th {
  color: var(--muted); font-weight: 600;
  font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.5px;
}
.min-rate { color: var(--accent); font-weight: 700; }
.threshold-met { font-style: normal; text-decoration: none; }
.empty-state {
  text-align: center; color: var(--warn);
  background: var(--warn-fade); border: 1px dashed #f5d27a;
  border-radius: 10px; padding: 20px; margin: 0 0 20px;
}
.calc-form {
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}
.calc-form label {
  display: flex; flex-direction: column;
  font-weight: 700; color: var(--muted);
  font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.5px;
}
.calc-form input, .calc-form select {
  margin-top: 6px; padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 6px;
  font-size: 0.95em; font-family: inherit; color: var(--text); background: var(--card);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.calc-form input:focus, .calc-form select:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-fade);
}
.calc-results { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.calc-prompt { color: var(--muted); font-style: italic; margin: 0; }
.calc-win { color: var(--accent); margin: 0 0 6px; font-weight: 700; font-size: 1em; }
.calc-neutral { color: var(--warn); margin: 0; font-weight: 600; }
.calc-results ul { font-size: 1.02em; line-height: 1.7; margin: 0; padding-left: 22px; }
.calc-results ul li b { color: var(--text); }
.chart-section {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: var(--shadow);
  margin-bottom: 24px; overflow: hidden;
}
.chart-section summary {
  padding: 14px 22px; cursor: pointer; list-style: none;
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 700; font-size: 0.74em; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.7px;
  user-select: none;
}
.chart-section summary::-webkit-details-marker { display: none; }
.chart-section summary::after {
  content: "▾"; display: inline-block; color: var(--muted);
  transition: transform 0.2s ease;
}
.chart-section[open] summary::after { transform: rotate(180deg); }
.chart-body { padding: 4px 22px 22px; }
.chart-controls {
  display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap;
  margin: 4px 0 14px;
}
.chart-controls label {
  display: flex; flex-direction: column;
  font-weight: 700; color: var(--muted);
  font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.5px;
}
.chart-controls select {
  margin-top: 6px; padding: 8px 12px;
  border: 1px solid var(--border); border-radius: 6px;
  font-size: 0.92em; font-family: inherit; color: var(--text); background: var(--card);
  min-width: 280px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chart-controls select:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-fade);
}
.chart-view[hidden], .trend-view[hidden] { display: none !important; }
.data-warning {
  background: var(--warn-fade); border: 1px solid #f5d27a;
  border-radius: 8px; padding: 10px 14px; margin: 0 0 14px;
  color: var(--warn); font-size: 0.88em; line-height: 1.5;
}
.data-warning.data-warning-ok {
  background: var(--accent-fade); border-color: #b6e8c8; color: var(--accent);
}
@media (max-width: 640px) {
  .calc-form { grid-template-columns: 1fr; }
  .topnav-inner { padding: 10px 16px; gap: 12px; }
  .brand { font-size: 0.95em; }
  .container { padding: 22px 16px 48px; }
  .util-card { padding: 12px 14px; }
  .page-header h1 { font-size: 1.4em; }
}
"""

    calculator_html = f"""
        <section class="card calculator-card" aria-label="Savings calculator">
            <h2 class="section-title" style="margin-top:0">Should I Switch?</h2>
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
        </section>
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

    elec_active = 'tab-active' if elecHtml else ''
    gas_active = 'tab-active' if not elecHtml else ''
    dash_type = 'electric' if elecHtml else 'gas'

    chart_switcher_js = (
        "<script>\n(function() {\n"
        "  var DASH = document.body.getAttribute('data-dashboard') || 'x';\n"
        "  function bind(selectId, viewAttr, viewClass) {\n"
        "    var sel = document.getElementById(selectId);\n"
        "    if (!sel) return;\n"
        "    var KEY = 'gAndETicker_' + selectId + '_' + DASH;\n"
        "    function showView(target) {\n"
        "      document.querySelectorAll('.' + viewClass).forEach(function(div) {\n"
        "        var match = div.getAttribute(viewAttr) === target;\n"
        "        div.hidden = !match;\n"
        "        if (match) {\n"
        "          var plot = div.querySelector('.js-plotly-plot');\n"
        "          if (plot && window.Plotly) {\n"
        "            setTimeout(function() { Plotly.Plots.resize(plot); }, 0);\n"
        "          }\n"
        "        }\n"
        "      });\n"
        "    }\n"
        "    var saved = localStorage.getItem(KEY);\n"
        "    if (saved && [].some.call(sel.options, function(o) { return o.value === saved; })) {\n"
        "      sel.value = saved;\n"
        "      showView(saved);\n"
        "    }\n"
        "    sel.addEventListener('change', function() {\n"
        "      localStorage.setItem(KEY, sel.value);\n"
        "      showView(sel.value);\n"
        "    });\n"
        "  }\n"
        "  bind('chart-view-select', 'data-view', 'chart-view');\n"
        "  bind('trends-view-select', 'data-trend', 'trend-view');\n"
        "})();\n</script>"
    )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{dashboard_title}</title>
    <style>{styles_block}</style>
</head>
<body data-dashboard="{dash_type}">
    <nav class="topnav">
        <div class="topnav-inner">
            <span class="brand">Ohio Energy Tracker</span>
            <div class="tabs">
                <a href="electric_dashboard.html" class="tab {elec_active}">Electric</a>
                <a href="gas_dashboard.html" class="tab {gas_active}">Gas</a>
            </div>
        </div>
    </nav>
    <main class="container">
        <header class="page-header">
            <h1>{dashboard_title}</h1>
            <p class="subtitle">Ohio energy choice rates as of {current_date_str}</p>
        </header>
        {calculator_html}
        <h2 class="section-title">Current Market Leaderboard</h2>
        <div class="leaderboard-cards">
            {"".join(table_sections)}
        </div>
        <details class="chart-section" open>
            <summary>Historical Trends</summary>
            <div class="chart-body">
                <div class="chart-controls">
                    <label>View
                        <select id="chart-view-select">
                            {chart_view_options}
                        </select>
                    </label>
                </div>
                {chart_views_html}
            </div>
        </details>
        <details class="chart-section">
            <summary>Long-term Trends &amp; Seasonality</summary>
            <div class="chart-body">
                <div class="chart-controls">
                    <label>View
                        <select id="trends-view-select">
                            {trend_view_options}
                        </select>
                    </label>
                </div>
                {trend_views_html}
            </div>
        </details>
    </main>
    {calculator_js}
    {chart_switcher_js}
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
