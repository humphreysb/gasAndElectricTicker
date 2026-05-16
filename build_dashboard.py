import json
from pathlib import Path
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
        url = f'https://www.google.com/search?q={cleaned_supplier + " BBB rating"}'
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

def _load_aggregation_rates():
    path = Path(__file__).parent / 'aggregation_rates.json'
    try:
        with open(path) as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}


AGGREGATION_RATES = _load_aggregation_rates()

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

    # --- 6. MARKET PULSE ENGINE ---
    this_month = datetime.now().month
    market_pulse_cards = []
    
    # Utilities in today's data
    util_today = today_df.groupby('Utility')['rate'].min().to_dict()
    
    # Historical distribution for this month
    hist_month = filtered_df[filtered_df['Date'].dt.month == this_month]
    
    for util, today_min in util_today.items():
        hist_util = hist_month[hist_month['Utility'] == util]['rate']
        if len(hist_util) > 5:
            # Calculate percentile (lower is better for consumer)
            percentile = (hist_util < today_min).mean() * 100
            
            if percentile < 15:
                status, color, icon = "Strong Signal", "var(--accent)", "🟢"
                advice = "Rates are near historical lows for this month. Excellent time to lock in a 12-24 month term."
            elif percentile < 35:
                status, color, icon = "Good Value", "var(--accent)", "🟢"
                advice = "Rates are below average. A good time to switch if your current contract is expiring."
            elif percentile < 65:
                status, color, icon = "Neutral", "var(--warn)", "🟡"
                advice = "Rates are at typical seasonal levels. Consider a shorter 6-month term to stay flexible."
            else:
                status, color, icon = "Wait if Possible", "#b91c1c", "🔴"
                advice = "Rates are currently higher than usual for this month. If possible, wait for a seasonal dip."
                
            market_pulse_cards.append(f"""
                <div class="stat-card" style="border-left: 4px solid {color}; text-align: left;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="stat-label">{util} Pulse</span>
                        <span style="font-size: 0.8em; font-weight: 800; color: {color};">{status}</span>
                    </div>
                    <div style="font-size: 1.1em; font-weight: 700; margin-bottom: 4px;">{icon} {percentile:.0f}th Percentile</div>
                    <div style="font-size: 0.75em; color: var(--muted); line-height: 1.3;">{advice}</div>
                </div>
            """)

    market_pulse_html = f"""
        <section class="card" style="padding: 0; overflow: hidden;">
            <div style="background: #f1f5f9; padding: 12px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted);">Market Pulse: Is now a good time to switch?</h2>
                <span style="font-size: 0.7em; font-weight: 700; color: var(--muted);">Based on 5Y Historical Data</span>
            </div>
            <div class="hero-stats" style="padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; justify-content: stretch;">
                {"".join(market_pulse_cards)}
            </div>
        </section>
    """ if market_pulse_cards else ""

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
