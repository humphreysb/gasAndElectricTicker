import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
import json
import re


def _clean_supplier_name(s):
    s = str(s) if s is not None else ''
    m = re.search(r'(?<=[a-zA-Z])\s*\.?\s*(?=\d)', s)
    if m:
        s = s[:m.start()]
    s = re.split(r'\s*P\.?\s*O\.?\s*Box', s, maxsplit=1, flags=re.IGNORECASE)[0]
    return s.rstrip(' ,.').strip()


def _load_bbb_ratings():
    path = Path(__file__).parent / 'bbb_ratings.json'
    try:
        with open(path) as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}


BBB_RATINGS = _load_bbb_ratings()


def _bbb_entry(cleaned_supplier):
    """Normalize a JSON entry into (rating, url). Accepts None, str (legacy), or dict."""
    raw = BBB_RATINGS.get(cleaned_supplier)
    rating, url = None, None
    if isinstance(raw, str):
        rating = raw
    elif isinstance(raw, dict):
        rating = raw.get('rating')
        url = raw.get('url')
    return rating, url


def _bbb_pill_html(cleaned_supplier):
    rating, url = _bbb_entry(cleaned_supplier)
    if not url:
        # Google "<supplier> BBB rating" is far more reliable than BBB's own search.
        url = f'https://www.google.com/search?q={quote_plus(cleaned_supplier + " BBB rating")}'
    if rating:
        head = rating.strip().upper().rstrip('+')[:1]
        if head in ('A', 'B'):
            cls = 'bbb-good'
        elif head in ('D', 'F'):
            cls = 'bbb-poor'
        else:
            cls = 'bbb-mid'
        title = f'BBB rating: {rating}'
        label = rating
    else:
        cls = 'bbb-unknown'
        title = 'No rating cached — click to look up'
        label = '—'
    return (
        f'<a class="bbb-pill {cls}" href="{url}" target="_blank" '
        f'rel="noopener" title="{title}">{label}</a>'
    )

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
        (
            (df['Supplier'] == 'Utility') | 
            (
                (df['Term. Length'] >= 6) &
                (df['Early Term. Fee'] == 0) &
                (df['Monthly Fee'] == 0)
            )
        )
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
        facet_row_spacing=min(0.02, 1.0 / max(num_terms, 2) * 0.5),
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

    # View 5: market min + weather overlay (temperature traces injected client-side via Open-Meteo)
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(
        x=market_min_day['Date'], y=market_min_day['rate'],
        mode='lines+markers',
        name=f'Market min ({unit})',
        line=dict(color='#15803d', width=3),
        marker=dict(color='#15803d', size=7),
    ))
    fig5.update_yaxes(range=y_range, title_text=f'Rate ({unit})')
    _style_chart(fig5, 480)
    fig5.update_layout(
        yaxis2=dict(
            title='Temperature (°F)',
            overlaying='y', side='right', showgrid=False,
            zeroline=False,
        ),
        margin=dict(t=30, b=40, l=55, r=55),
    )
    # Give this figure's wrapping div an id we can target from JS
    fig5.update_layout(meta={'weather_chart': True})

    chart_views_meta = [
        ('by-utility', 'Each utility, all terms',                fig1),
        ('by-term',    'Each term, all utilities',               fig2),
        ('cheap-util', 'Cheapest rate per utility',              fig3),
        ('market-min', 'Market minimum (cheapest rate anywhere)', fig4),
        ('weather',    'Market minimum + Ohio weather overlay',   fig5),
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

    # --- EIA macro overlay (Ohio residential state-average rate) ---
    eia_path = Path(__file__).parent / 'eiaData.parquet'
    eia_monthly = pd.DataFrame()
    eia_yearly = pd.DataFrame()
    eia_season = pd.DataFrame()
    if eia_path.exists():
        try:
            _eia = pd.read_parquet(eia_path)
            _eia = _eia[_eia['electric'] == elecHtml].copy()
            if not _eia.empty:
                _eia['Date'] = pd.to_datetime(_eia['Date'])
                _eia = _eia.sort_values('Date')
                eia_monthly = _eia[['Date', 'rate']].copy()
                eia_yearly = (
                    _eia.assign(Year=_eia['Date'].dt.year)
                        .groupby('Year')['rate'].mean().reset_index()
                )
                eia_season = (
                    _eia.assign(Month=_eia['Date'].dt.month)
                        .groupby('Month')['rate'].mean().reset_index()
                )
        except Exception as _e:
            print(f"EIA overlay disabled: {_e}")

    def _trend_line(df_in, title_y, height, eia_df=None):
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
        if eia_df is not None and not eia_df.empty:
            f.add_trace(go.Scatter(
                x=eia_df['Date'], y=eia_df['rate'], mode='lines',
                name='Ohio residential avg (EIA)',
                line=dict(color='#3b82f6', width=2, dash='dash'),
            ))
        f.update_yaxes(title_text=title_y)
        return _style_chart(f, height)

    fig_weekly = _trend_line(weekly_summary, f'Rate ({unit})', 420)
    fig_monthly = _trend_line(monthly_summary, f'Rate ({unit})', 420, eia_df=eia_monthly)

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
    if not eia_yearly.empty:
        fig_yearly.add_trace(go.Bar(
            x=eia_yearly['Year'].astype(str), y=eia_yearly['rate'],
            name='Ohio residential avg (EIA)', marker=dict(color='#3b82f6'),
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
    if not eia_season.empty:
        eia_season = eia_season.copy()
        eia_season['MonthName'] = eia_season['Month'].map(lambda m: MONTH_NAMES[int(m) - 1])
        fig_season.add_trace(go.Scatter(
            x=eia_season['MonthName'], y=eia_season['rate'],
            mode='lines+markers', name='Ohio residential avg (EIA, 25-yr)',
            line=dict(color='#3b82f6', width=2, dash='dash'),
            marker=dict(size=8, color='#3b82f6'),
        ))
    fig_season.update_yaxes(title_text=f'Avg rate ({unit})')
    fig_season.update_xaxes(title_text='Calendar month')
    _style_chart(fig_season, 460, show_legend=not eia_season.empty)

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
            section += f"<table><thead><tr><th>Supplier</th><th>BBB</th><th>Term</th><th>Rate ({unit})</th></tr></thead><tbody>"

            for _, row in u_data.iterrows():
                # Bold if it's the absolute best value for this utility
                is_best_val = (row['rate'] == best_overall_rate)
                is_below_thresh = threshold_rate is not None and row['rate'] < threshold_rate

                cell_class = "min-rate" if is_best_val else ""
                if is_below_thresh: cell_class += " threshold-met"

                rate_display = f"{row['rate']:.5f}"
                if is_best_val: rate_display = f"<b>{rate_display}</b>"

                supplier_clean = _clean_supplier_name(row['Supplier'])
                bbb_html = _bbb_pill_html(supplier_clean)

                section += (
                    f"<tr><td>{supplier_clean}</td><td>{bbb_html}</td>"
                    f"<td>{row['Term. Length']} Mo</td>"
                    f"<td class='{cell_class}'>{rate_display}</td></tr>"
                )
            section += "</tbody></table></article>"
            table_sections.append(section)
    else:
        table_sections = ['<p class="empty-state">No new data has been updated for today yet.</p>']

    # --- 6c. TOP 5 RATES SECTION DATA ---
    if not today_df.empty:
        today_clean = today_df.copy()
        today_clean['SupplierClean'] = today_clean['Supplier'].apply(_clean_supplier_name)
        today_dedup = (
            today_clean.groupby(['Utility', 'SupplierClean', 'Term. Length'], as_index=False)['rate']
                       .min()
                       .sort_values('rate')
        )
        unique_terms = sorted({int(t) for t in today_dedup['Term. Length'].unique()})
        top_rates_buckets = {'all': []}
        for t in unique_terms:
            top_rates_buckets[str(t)] = []
        for _, row in today_dedup.iterrows():
            rating, url = _bbb_entry(row['SupplierClean'])
            entry = {
                'utility': row['Utility'],
                'supplier': row['SupplierClean'],
                'term': int(row['Term. Length']),
                'rate': float(row['rate']),
                'bbb': rating,
                'bbb_url': url,
            }
            if len(top_rates_buckets['all']) < 5:
                top_rates_buckets['all'].append(entry)
            tkey = str(entry['term'])
            if tkey in top_rates_buckets and len(top_rates_buckets[tkey]) < 5:
                top_rates_buckets[tkey].append(entry)
        top_rates_payload = {'unit': unit, 'data': top_rates_buckets}
        top_rates_term_options = '<option value="all">All terms</option>' + "".join(
            f'<option value="{t}">{t} months</option>' for t in unique_terms
        )
        top_rates_available = True
    else:
        top_rates_payload = {'unit': unit, 'data': {'all': []}}
        top_rates_term_options = '<option value="all">All terms</option>'
        top_rates_available = False
    top_rates_payload_json = json.dumps(top_rates_payload)

    if top_rates_available:
        top_rates_section_html = f"""
        <section class="card top-rates-card">
            <h2 class="section-title" style="margin-top:0">Top 5 Rates Right Now</h2>
            <div class="top-rates-controls">
                <label>Filter by term
                    <select id="top-rates-term-select">{top_rates_term_options}</select>
                </label>
            </div>
            <table class="top-rates-table">
                <thead>
                    <tr><th>#</th><th>Utility</th><th>Supplier</th><th>BBB</th><th>Term</th><th>Rate ({unit})</th></tr>
                </thead>
                <tbody id="top-rates-tbody"></tbody>
            </table>
        </section>
"""
    else:
        top_rates_section_html = ''

    top_rates_js = (
        "<script>\n(function() {\n"
        "  var PAYLOAD = " + top_rates_payload_json + ";\n"
        "  var sel = document.getElementById('top-rates-term-select');\n"
        "  var tbody = document.getElementById('top-rates-tbody');\n"
        "  if (!sel || !tbody) return;\n"
        "  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }\n"
        "  function bbbPill(supplier, rating, url) {\n"
        "    var href = url || ('https://www.google.com/search?q=' + encodeURIComponent(supplier + ' BBB rating'));\n"
        "    if (rating) {\n"
        "      var head = rating.trim().toUpperCase().replace('+', '').substring(0, 1);\n"
        "      var cls = (head === 'A' || head === 'B') ? 'bbb-good' : (head === 'D' || head === 'F') ? 'bbb-poor' : 'bbb-mid';\n"
        "      return '<a class=\"bbb-pill ' + cls + '\" href=\"' + href + '\" target=\"_blank\" rel=\"noopener\" title=\"BBB rating: ' + esc(rating) + '\">' + esc(rating) + '</a>';\n"
        "    }\n"
        "    return '<a class=\"bbb-pill bbb-unknown\" href=\"' + href + '\" target=\"_blank\" rel=\"noopener\" title=\"No rating cached — click to look up\">—</a>';\n"
        "  }\n"
        "  function render() {\n"
        "    var term = sel.value;\n"
        "    var rows = (PAYLOAD.data[term] || []);\n"
        "    if (rows.length === 0) {\n"
        "      tbody.innerHTML = '<tr><td colspan=\"6\" class=\"empty-cell\">No data for that term.</td></tr>';\n"
        "      return;\n"
        "    }\n"
        "    tbody.innerHTML = rows.map(function(r, i) {\n"
        "      return '<tr>' +\n"
        "        '<td class=\"rank-cell\">' + (i + 1) + '</td>' +\n"
        "        '<td>' + esc(r.utility) + '</td>' +\n"
        "        '<td>' + esc(r.supplier) + '</td>' +\n"
        "        '<td>' + bbbPill(r.supplier, r.bbb, r.bbb_url) + '</td>' +\n"
        "        '<td>' + r.term + ' Mo</td>' +\n"
        "        '<td class=\"rate-cell\">' + r.rate.toFixed(5) + '</td>' +\n"
        "      '</tr>';\n"
        "    }).join('');\n"
        "  }\n"
        "  var KEY = 'gAndETicker_top_rates_term_' + (document.body.getAttribute('data-dashboard') || 'x');\n"
        "  var saved = localStorage.getItem(KEY);\n"
        "  if (saved && [].some.call(sel.options, function(o) { return o.value === saved; })) {\n"
        "    sel.value = saved;\n"
        "  }\n"
        "  sel.addEventListener('change', function() {\n"
        "    localStorage.setItem(KEY, sel.value);\n"
        "    render();\n"
        "  });\n"
        "  render();\n"
        "})();\n</script>"
    )

    # --- 6. RATE REALITY CHECK ENGINE ---
    # Premise: comparing today's best market rate against the historical *minimum*
    # (the best deal that was actually available) is what consumers actually want
    # to know. A rate at the 30th percentile of last year still might be 20%+
    # worse than what was available 6 months ago — and that's the truth a
    # consumer needs to make a switching decision.
    today_dt = today_df['Date'].max()

    timeframes = {
        '6mo': 180,
        '1y': 365,
        '3y': 365*3,
        '5y': 365*5
    }

    pulse_data = {}
    util_today = today_df.groupby('Utility')['rate'].min().to_dict()

    rate_fmt = (lambda r: f"{r*100:.2f}¢/kWh") if elecHtml else (lambda r: f"${r:.2f}/MCF")

    for timeframe_id, days in timeframes.items():
        cutoff = today_dt - pd.Timedelta(days=days)
        hist_tf = filtered_df[filtered_df['Date'] >= cutoff]

        for util, today_min in util_today.items():
            if util not in pulse_data: pulse_data[util] = {}

            hist_util = hist_tf[hist_tf['Utility'] == util]['rate']
            if len(hist_util) < 30:
                continue

            hist_low = float(hist_util.min())
            hist_median = float(hist_util.median())
            # premium = how much more today costs vs the historical low
            premium_pct = (today_min / hist_low - 1) * 100 if hist_low > 0 else 0

            window_label = {'6mo': '6 months', '1y': 'year', '3y': '3 years', '5y': '5 years'}[timeframe_id]

            if premium_pct < 5:
                status, color, icon = f"Near {window_label} low", "#16a34a", "🟢"
                advice = f"Today's best rate is within 5% of the lowest available in the past {window_label}. Strong moment to lock in a longer term."
            elif premium_pct < 15:
                status, color, icon = "Slight premium", "#65a30d", "🟢"
                advice = f"Reasonable rate, but {premium_pct:.0f}% above the best deal seen in the past {window_label}. Worth locking in if your contract is expiring."
            elif premium_pct < 30:
                status, color, icon = "Notable premium", "#d97706", "🟡"
                advice = f"You'd pay {premium_pct:.0f}% more than the best rate seen in the past {window_label} ({rate_fmt(hist_low)}). If your contract isn't expiring soon, wait."
            else:
                status, color, icon = "Poor timing", "#b91c1c", "🔴"
                advice = f"Today's best is {premium_pct:.0f}% above the {window_label} low of {rate_fmt(hist_low)}. Switching now locks in elevated pricing — wait if your current contract allows."

            pulse_data[util][timeframe_id] = {
                'today_rate': rate_fmt(today_min),
                'hist_low': rate_fmt(hist_low),
                'hist_median': rate_fmt(hist_median),
                'premium_pct': round(premium_pct),
                'status': status,
                'color': color,
                'icon': icon,
                'advice': advice
            }

    pulse_data_json = json.dumps(pulse_data)

    market_pulse_html = f"""
        <section class="card" style="padding: 0; overflow: hidden;">
            <div style="background: #f1f5f9; padding: 12px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <h2 style="margin: 0; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted);">Rate Reality Check: How does today's best deal stack up?</h2>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.7em; font-weight: 700; color: var(--muted);">COMPARE AGAINST:</span>
                    <select id="pulse-timeline" style="padding: 4px 8px; border-radius: 6px; border: 1px solid var(--border); font-size: 0.75em; font-weight: 700; color: var(--text);">
                        <option value="6mo">Last 6 Months</option>
                        <option value="1y" selected>Last 1 Year</option>
                        <option value="3y">Last 3 Years</option>
                        <option value="5y">Last 5 Years</option>
                    </select>
                </div>
            </div>
            <div id="market-pulse-grid" class="hero-stats" style="padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; justify-content: stretch;">
                <!-- JavaScript will populate cards here -->
            </div>
            <div style="background: #f8fafc; padding: 8px 24px; border-top: 1px solid var(--border); font-size: 0.7em; color: var(--muted); text-align: center;">
                Each card compares today's best market rate to the lowest rate actually available in the selected window. A "premium" means you'd pay that much more than the best deal recently seen.
            </div>
        </section>
    """ if pulse_data else ""

    pulse_js = f"""
<script>
(function() {{
    const PULSE_DATA = {pulse_data_json};
    const grid = document.getElementById('market-pulse-grid');
    const select = document.getElementById('pulse-timeline');
    
    function renderPulse(timeframe) {{
        if (!grid) return;
        let html = '';
        for (const [util, tfData] of Object.entries(PULSE_DATA)) {{
            const data = tfData[timeframe];
            if (!data) continue;
            
            const premiumLabel = data.premium_pct <= 0 ? 'At the low' : `+${{data.premium_pct}}% above low`;
            html += `
                <div class="stat-card" style="border-left: 4px solid ${{data.color}}; text-align: left;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="stat-label">${{util}}</span>
                        <span style="font-size: 0.8em; font-weight: 800; color: ${{data.color}};">${{data.icon}} ${{data.status}}</span>
                    </div>
                    <div style="font-size: 1.15em; font-weight: 800; margin-bottom: 2px;">${{data.today_rate}} <span style="font-size: 0.7em; font-weight: 700; color: ${{data.color}};">(${{premiumLabel}})</span></div>
                    <div style="font-size: 0.7em; color: var(--muted); margin-bottom: 8px;">Window low: ${{data.hist_low}} · median: ${{data.hist_median}}</div>
                    <div style="font-size: 0.75em; color: var(--text); line-height: 1.4;">${{data.advice}}</div>
                </div>
            `;
        }}
        grid.innerHTML = html || '<p style="grid-column: 1/-1; text-align: center; color: var(--muted); font-size: 0.9em; padding: 20px;">Insufficient historical data for this timeline.</p>';
    }}
    
    if (select) {{
        select.addEventListener('change', (e) => renderPulse(e.target.value));
        renderPulse('1y');
    }}
}})();
</script>
"""

    # --- 7. ASSEMBLE FINAL HTML ---
    dashboard_title = "Electric Dashboard" if elecHtml else "Gas Dashboard"
    other_dash = "Gas" if elecHtml else "Electric"
    other_url = "gas_dashboard.html" if elecHtml else "electric_dashboard.html"
    icon = "⚡" if elecHtml else "🔥"
    
    hero_section = f"""
        <header class="hero">
            <div class="hero-content">
                <div class="hero-badge">{icon} Ohio {dashboard_title.split()[0]} Market (Experimental)</div>
                <h1>Explore Energy Options</h1>
                <p class="hero-lead">
                    This free community tool tracks the <strong>Apples to Apples</strong> marketplace daily, attempting to filter out complex "fine print" 
                    to highlight more straightforward, fixed-rate plans. <strong>Data is automated and not guaranteed.</strong>
                </p>
                <div class="hero-stats">
                    <div class="stat-card">
                        <span class="stat-value">{current_date_str}</span>
                        <span class="stat-label">Last Updated</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-value">{len(today_df)}</span>
                        <span class="stat-label">Verified Plans</span>
                    </div>
                </div>
            </div>
        </header>
    """

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
  --bg: #f8fafc;
  --card: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --accent: #16a34a;
  --accent-fade: #f0fdf4;
  --warn: #d97706;
  --warn-fade: #fffbeb;
  --primary: #2563eb;
  --primary-fade: #eff6ff;
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.topnav {
  position: sticky; top: 0; z-index: 100;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}
.topnav-inner {
  max-width: 1200px; margin: 0 auto;
  padding: 12px 24px;
  display: flex; align-items: center; justify-content: space-between;
}
.brand { font-weight: 800; font-size: 1.1em; color: var(--text); letter-spacing: -0.02em; }
.tabs { display: flex; gap: 8px; }
.tab {
  text-decoration: none; padding: 8px 16px; border-radius: 8px;
  color: var(--muted); font-weight: 600; font-size: 0.9em;
  transition: all 0.2s;
}
.tab:hover { background: var(--bg); color: var(--text); }
.tab-active { background: var(--text); color: white; }

.hero {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: white; padding: 60px 24px; text-align: center;
  margin-bottom: 40px;
}
.hero-content { max-width: 800px; margin: 0 auto; }
.hero-badge {
  display: inline-block; background: rgba(255,255,255,0.1);
  padding: 4px 12px; border-radius: 20px; font-size: 0.85em;
  font-weight: 600; margin-bottom: 16px; border: 1px solid rgba(255,255,255,0.2);
}
.hero h1 {
  font-size: 2.75em; font-weight: 800; margin: 0 0 16px;
  letter-spacing: -0.03em; line-height: 1.1;
}
.hero-lead { font-size: 1.15em; color: #94a3b8; margin-bottom: 32px; }
.hero-stats { display: flex; justify-content: center; gap: 24px; }
.stat-card {
  background: rgba(255,255,255,0.05); padding: 12px 24px;
  border-radius: 12px; border: 1px solid rgba(255,255,255,0.1);
}
.stat-value { display: block; font-size: 1.2em; font-weight: 700; color: white; }
.stat-label { font-size: 0.75em; color: #64748b; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }

.container { max-width: 1200px; margin: 0 auto; padding: 0 24px 80px; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 24px;
  margin-bottom: 24px; box-shadow: var(--shadow-sm);
}
.section-title {
  margin: 40px 0 16px;
  font-size: 0.85em; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--muted);
}
.leaderboard-cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 20px; margin-bottom: 24px;
}
@media (max-width: 1100px) { .leaderboard-cards { grid-template-columns: 1fr; } }

.util-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 20px; box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column;
}
.util-card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
}
.util-card-head h3 { margin: 0; font-size: 1.2em; font-weight: 700; }

.pill {
  display: inline-block; padding: 4px 12px;
  border-radius: 20px; font-size: 0.75em; font-weight: 600;
}
.pill-rate { background: var(--primary-fade); color: var(--primary); }
.badge-90d-low {
  background: var(--accent); color: white;
  padding: 4px 12px; border-radius: 20px;
  font-size: 0.7em; font-weight: 700;
}

.util-card table { width: 100%; border-collapse: collapse; }
.calculator-card { margin-bottom: 0 !important; }
.util-card th, .util-card td {
  padding: 10px 8px; text-align: left; font-size: 0.9em;
  border-bottom: 1px solid #f1f5f9;
}
.util-card th {
  color: var(--muted); font-weight: 600;
  font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em;
}
.min-rate { color: var(--accent); font-weight: 700; }

.calc-form { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
.calc-form label { font-size: 0.75em; font-weight: 700; color: var(--muted); text-transform: uppercase; }
.calc-form input, .calc-form select {
  width: 100%; margin-top: 8px; padding: 12px;
  border: 1px solid var(--border); border-radius: 10px;
  background: #f8fafc; font-size: 1em;
}

.chart-section {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; margin-bottom: 24px; overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.chart-section summary {
  padding: 20px 24px; cursor: pointer; font-weight: 700;
  color: var(--text); display: flex; justify-content: space-between;
  background: #f8fafc; border-bottom: 1px solid var(--border);
}
.chart-body { padding: 24px; }
.chart-controls select {
  padding: 10px 16px; border-radius: 10px; border: 1px solid var(--border);
  font-weight: 600; min-width: 300px;
}

.top-rates-table { width: 100%; border-collapse: collapse; }
.top-rates-table th, .top-rates-table td { padding: 12px; border-bottom: 1px solid var(--border); }
.top-rates-table th { font-size: 0.75em; color: var(--muted); text-transform: uppercase; }
.rank-cell { font-weight: 800; color: var(--muted); width: 40px; }
.rate-cell { color: var(--accent); font-weight: 800; font-size: 1.1em; }

.bbb-pill {
  display: inline-block; padding: 2px 10px; border-radius: 6px;
  font-weight: 700; font-size: 0.8em; text-decoration: none;
}
.bbb-good { background: #dcfce7; color: #166534; }
.bbb-poor { background: #fee2e2; color: #991b1b; }
.bbb-mid { background: #fef3c7; color: #92400e; }

@media (max-width: 768px) {
  .hero h1 { font-size: 2em; }
  .calc-form { grid-template-columns: 1fr; }
  .hero-stats { flex-direction: column; gap: 12px; }
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
            <div id="calc-share-container" style="display:none; margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px; text-align: right;">
                <button id="btn-share" class="btn" style="background: var(--primary); color: white; padding: 8px 16px; font-size: 0.85em; cursor: pointer; border: none; box-shadow: var(--shadow-sm);">
                    🔗 Share My Savings
                </button>
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
        "    saveInputs();\n"
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
        "    $('calc-share-container').style.display = (monthlyDiff > 0) ? 'block' : 'none';\n"
        "  }\n"
        "  document.addEventListener('DOMContentLoaded', function() {\n"
        "    loadInputs();\n"
        "    IDS.forEach(function(id) {\n"
        "      var el = $(id);\n"
        "      el.addEventListener('input', render);\n"
        "      el.addEventListener('change', function() {\n"
        "        render();\n"
        "      });\n"
        "    });\n"
        "\n"
        "    // Share Logic\n"
        "    $('btn-share').addEventListener('click', function() {\n"
        "      var util = $('calc-utility').value;\n"
        "      var myRate = parseFloat($('calc-current-rate').value);\n"
        "      var usage = parseFloat($('calc-usage').value);\n"
        "      var minRate = DATA.min_by_util[util];\n"
        "      var yearlyDiff = (myRate - minRate) * usage * 12;\n"
        "      var msg = 'I could save ' + fmtMoney(yearlyDiff) + ' / year on my ' + DATA.dashboard_type + ' bill! Check your savings at the Ohio Energy Tracker: ' + window.location.href;\n"
        "      if (navigator.share) {\n"
        "        navigator.share({ title: 'Ohio Energy Tracker', text: msg, url: window.location.href }).catch(function(e) { console.error('Error sharing:', e); });\n"
        "      } else {\n"
        "        navigator.clipboard.writeText(msg).then(function() {\n"
        "          alert('Sharing message copied to clipboard!');\n"
        "        });\n"
        "      }\n"
        "    });\n"
        "\n"
        "    render();\n"
        "  });\n"
        "})();\n</script>"
    )

    elec_active = 'tab-active' if elecHtml else ''
    gas_active = 'tab-active' if not elecHtml else ''
    dash_type = 'electric' if elecHtml else 'gas'

    weather_js = (
        "<script>\n(function() {\n"
        "  var LAT = 39.96, LON = -82.99;\n"  # Columbus, Ohio
        "  var CACHE_KEY = 'gAndETicker_weather_v1';\n"
        "  var CACHE_TTL_MS = 12 * 60 * 60 * 1000;\n"
        "  function loadCache() {\n"
        "    try {\n"
        "      var raw = localStorage.getItem(CACHE_KEY);\n"
        "      if (!raw) return null;\n"
        "      var obj = JSON.parse(raw);\n"
        "      if (Date.now() - obj.ts > CACHE_TTL_MS) return null;\n"
        "      return obj.data;\n"
        "    } catch (e) { return null; }\n"
        "  }\n"
        "  function saveCache(data) {\n"
        "    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ts: Date.now(), data: data})); } catch (e) {}\n"
        "  }\n"
        "  function fetchWeather() {\n"
        "    var cached = loadCache();\n"
        "    if (cached) return Promise.resolve(cached);\n"
        "    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON +\n"
        "      '&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min&past_days=92&forecast_days=14' +\n"
        "      '&temperature_unit=fahrenheit&timezone=America%2FNew_York';\n"
        "    return fetch(url).then(function(r) { if (!r.ok) throw new Error('open-meteo ' + r.status); return r.json(); })\n"
        "      .then(function(data) { saveCache(data); return data; });\n"
        "  }\n"
        "  function findWeatherChart() {\n"
        "    var views = document.querySelectorAll('.chart-view[data-view=\"weather\"] .js-plotly-plot');\n"
        "    return views[0] || null;\n"
        "  }\n"
        "  function applyOverlay(chartDiv, wx) {\n"
        "    if (!chartDiv || !window.Plotly || !wx || !wx.daily) return;\n"
        "    var dates = wx.daily.time;\n"
        "    var tMean = wx.daily.temperature_2m_mean;\n"
        "    var tMax = wx.daily.temperature_2m_max;\n"
        "    var tMin = wx.daily.temperature_2m_min;\n"
        "    var today = new Date().toISOString().slice(0, 10);\n"
        "    var splitIdx = dates.findIndex(function(d) { return d > today; });\n"
        "    if (splitIdx < 0) splitIdx = dates.length;\n"
        "    var histX = dates.slice(0, splitIdx);\n"
        "    var histY = tMean.slice(0, splitIdx);\n"
        "    var fcX = dates.slice(Math.max(splitIdx - 1, 0));\n"
        "    var fcY = tMean.slice(Math.max(splitIdx - 1, 0));\n"
        "    var bandX = dates.concat([].slice.call(dates).reverse());\n"
        "    var bandY = tMax.concat([].slice.call(tMin).reverse());\n"
        "    var traces = [\n"
        "      { x: bandX, y: bandY, fill: 'toself', fillcolor: 'rgba(59, 130, 246, 0.08)',\n"
        "        line: {color: 'rgba(0,0,0,0)'}, name: 'Temp range (min/max)', yaxis: 'y2',\n"
        "        hoverinfo: 'skip', showlegend: true, type: 'scatter' },\n"
        "      { x: histX, y: histY, mode: 'lines', name: 'Temp mean (°F)', yaxis: 'y2',\n"
        "        line: {color: '#3b82f6', width: 2}, type: 'scatter' },\n"
        "      { x: fcX, y: fcY, mode: 'lines', name: 'Temp forecast', yaxis: 'y2',\n"
        "        line: {color: '#3b82f6', width: 2, dash: 'dot'}, type: 'scatter' }\n"
        "    ];\n"
        "    Plotly.addTraces(chartDiv, traces);\n"
        "    Plotly.relayout(chartDiv, {\n"
        "      shapes: [{ type: 'line', x0: today, x1: today, yref: 'paper', y0: 0, y1: 1,\n"
        "                 line: {color: '#9ca3af', width: 1, dash: 'dash'} }],\n"
        "      annotations: [{ x: today, y: 1, yref: 'paper', text: 'today', showarrow: false,\n"
        "                      yanchor: 'bottom', font: {size: 10, color: '#9ca3af'} }]\n"
        "    });\n"
        "  }\n"
        "  function init() {\n"
        "    var chartDiv = findWeatherChart();\n"
        "    if (!chartDiv) return;\n"
        "    if (chartDiv.dataset.weatherLoaded === '1') return;\n"
        "    chartDiv.dataset.weatherLoaded = '1';\n"
        "    fetchWeather().then(function(wx) { applyOverlay(chartDiv, wx); })\n"
        "      .catch(function(err) { console.warn('Weather overlay unavailable:', err); chartDiv.dataset.weatherLoaded = '0'; });\n"
        "  }\n"
        "  if (document.readyState === 'loading') {\n"
        "    document.addEventListener('DOMContentLoaded', init);\n"
        "  } else {\n"
        "    init();\n"
        "  }\n"
        "})();\n</script>"
    )

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
    <title>Ohio {dashboard_title}</title>
    <meta property="og:title" content="Ohio {dashboard_title}">
    <meta property="og:description" content="Track daily energy rates in Ohio and find the best fixed-rate plans.">
    <meta property="og:type" content="website">
    <meta name="description" content="Free, open-source tracker for Ohio energy rates. Compare utility supply charges daily.">
    <link rel="manifest" href="manifest.json">
    <meta name="theme-color" content="#0f172a">
    <link rel="apple-touch-icon" href="icon-192.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>{styles_block}</style>
    </head>
    <body data-dashboard="{dash_type}">
    <script>
    if ('serviceWorker' in navigator) {{
    window.addEventListener('load', () => {{
    const swPath = window.location.pathname.includes('gasAndElectricTicker')
    ? '/gasAndElectricTicker/sw.js'
    : './sw.js';
    navigator.serviceWorker.register(swPath)
    .then(reg => console.log('SW registered!', reg))
    .catch(err => console.error('SW registration failed:', err));
    }});
    }}
    </script>
    <nav class="topnav">
    <div class="topnav-inner">
    <span class="brand">Ohio Energy Tracker</span>
    <div class="tabs">
    <a href="electric_dashboard.html" class="tab {elec_active}">Electric</a>
    <a href="gas_dashboard.html" class="tab {gas_active}">Gas</a>
    </div>
    </div>
    </nav>
    {hero_section}
    <main class="container">
    <p style="margin-top: -24px; margin-bottom: 32px; font-size: 0.85em; font-style: italic; color: #94a3b8; text-align: center;">
    * This is a free open-source project. Rates are automated and may contain errors. Always verify data on official provider websites.
    </p>
    {top_rates_section_html}
    {market_pulse_html}
    {calculator_html}
    <h2 class="section-title">Market Leaderboard</h2>
    <div class="leaderboard-cards">
    {"".join(table_sections)}
    </div>
    <details class="chart-section" open>
    <summary>Market Dynamics</summary>
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
    {top_rates_js}
    {chart_switcher_js}
    {weather_js}
    {pulse_js}
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
