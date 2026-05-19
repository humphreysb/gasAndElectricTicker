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
import providers

def generate_energy_dashboard(file_path, html_file_name, elecHtml, top_link_url, top_link_text, threshold_rate, state='OH'):
    # --- 2. LOAD & INITIAL FILTERING ---
    df = pd.read_parquet(file_path)

    # Backfill state for any rows scraped before the multi-state column existed.
    if 'state' not in df.columns:
        df['state'] = 'OH'
    else:
        df['state'] = df['state'].fillna('OH')

    base_mask = (
        (df['state'] == state) &
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
    state_util_map = providers.for_state(state)
    util_map = state_util_map['elec'] if elecHtml else state_util_map['gas']
    filtered_df['Utility'] = filtered_df['Provider'].map(util_map)
    
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

    # --- EIA macro overlay (state-average rate) ---
    eia_path = Path(__file__).parent / 'eiaData.parquet'
    eia_monthly = pd.DataFrame()
    eia_yearly = pd.DataFrame()
    eia_season = pd.DataFrame()
    if eia_path.exists():
        try:
            _eia = pd.read_parquet(eia_path)
            # Filter by electric/gas AND state
            _mask = (_eia['electric'] == elecHtml)
            if 'state' in _eia.columns:
                _mask &= (_eia['state'] == state)
            
            _eia = _eia[_mask].copy()
            
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
        # Get the best supplier per Provider and Term Length
        today_min = today_df.loc[today_df.groupby(['Provider', 'Term. Length'])['rate'].idxmin()]
        providers_ids = sorted(today_min['Provider'].unique())

        for pid in providers_ids:
            u_data = today_min[today_min['Provider'] == pid].sort_values(['Term. Length', 'rate'])
            util_name = u_data['Utility'].iloc[0]
            best_overall_rate = u_data['rate'].min()
            current_min = current_min_by_util.get(util_name, best_overall_rate)

            badge_html = '<span class="badge-90d-low" title="Today\'s minimum matches the lowest rate in the last 90 days">90-DAY LOW</span>' if is_90d_low_by_util.get(util_name, False) else ''
            rate_pill = f'<span class="pill pill-rate">Min today: {current_min:.5f} {unit}</span>'

            section = f'<article class="util-card" data-utility="{pid}">'
            section += f'<header class="util-card-head"><h3>{util_name}</h3>{rate_pill}{badge_html}</header>'
            section += f"<table><thead><tr><th>Supplier</th><th>BBB</th><th>Term</th><th>Rate ({unit})</th><th></th></tr></thead><tbody>"

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

                calc_btn = f'<button class="btn-calc-small" onclick="window.__useInCalculator(event, {row["rate"]:.5f}, \'{supplier_clean}\')" title="Select this plan for the savings calculator">Compare</button>'

                section += (
                    f"<tr><td>{supplier_clean}</td><td>{bbb_html}</td>"
                    f"<td>{row['Term. Length']} Mo</td>"
                    f"<td class='{cell_class}'>{rate_display}</td>"
                    f"<td>{calc_btn}</td></tr>"
                )
            section += "</tbody></table></article>"
            table_sections.append(section)
    else:
        table_sections = ['<p class="empty-state">No new data has been updated for today yet.</p>']

    # --- 6c. TOP 5 RATES SECTION DATA ---
    TOP_N = 3
    if not today_df.empty:
        today_clean = today_df.copy()
        today_clean['SupplierClean'] = today_clean['Supplier'].apply(_clean_supplier_name)
        today_dedup = (
            today_clean.groupby(['Provider', 'Utility', 'SupplierClean', 'Term. Length'], as_index=False)['rate']
                       .min()
                       .sort_values('rate')
        )
        unique_terms = [t for t in [1, 6, 12, 24, 36] if t in today_dedup['Term. Length'].unique()]

        # Build aggregate buckets (top N across all utilities) + per-utility buckets
        top_rates_buckets = {'all': []}
        for t in unique_terms:
            top_rates_buckets[str(t)] = []

        by_util = {}  # { provider_id_str: { 'all': [...], '12': [...] } }

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
            tkey = str(entry['term'])

            if len(top_rates_buckets['all']) < TOP_N:
                top_rates_buckets['all'].append(entry)
            if tkey in top_rates_buckets and len(top_rates_buckets[tkey]) < TOP_N:
                top_rates_buckets[tkey].append(entry)

            pid = str(row['Provider'])
            if pid not in by_util:
                by_util[pid] = {'all': []}
                for t in unique_terms:
                    by_util[pid][str(t)] = []
            
            if len(by_util[pid]['all']) < TOP_N:
                by_util[pid]['all'].append(entry)
            if tkey in by_util[pid] and len(by_util[pid][tkey]) < TOP_N:
                by_util[pid][tkey].append(entry)

        top_rates_payload = {'unit': unit, 'data': top_rates_buckets, 'by_util': by_util, 'top_n': TOP_N}
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
            <h2 class="section-title" style="margin-top:0" id="top-rates-heading">Top 3 Rates Right Now</h2>
            <div class="top-rates-controls">
                <label>Filter by term
                    <select id="top-rates-term-select">{top_rates_term_options}</select>
                </label>
            </div>
            <table class="top-rates-table">
                <thead>
                    <tr><th>#</th><th>Utility</th><th>Supplier</th><th>BBB</th><th>Term</th><th>Rate ({unit})</th><th></th></tr>
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
      "  var FUEL = document.body.getAttribute('data-dashboard') || 'electric';\n"
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
      "  function getSelectedUtility() {\n"
      "    try {\n"
      "      var saved = JSON.parse(localStorage.getItem('oet_selection_v1') || '{}');\n"
      "      var u = saved.utilities && saved.utilities[FUEL];\n"
      "      return (u && u !== 'all') ? u : null;\n"
      "    } catch (e) { return null; }\n"
      "  }\n"
      "  function render() {\n"
      "    var term = sel.value;\n"
      "    var util = getSelectedUtility();\n"
      "    var rows;\n"
      "    if (util && PAYLOAD.by_util && PAYLOAD.by_util[util]) {\n"
      "      rows = PAYLOAD.by_util[util][term] || [];\n"
      "    } else {\n"
      "      rows = PAYLOAD.data[term] || [];\n"
      "    }\n"
      "    var heading = document.getElementById('top-rates-heading');\n"
      "    if (heading) {\n"
      "      var n = PAYLOAD.top_n || 3;\n"
      "      var label = util;\n"
      "      if (util && typeof UTILITIES !== 'undefined' && UTILITIES[FUEL]) {\n"
      "        var uObj = UTILITIES[FUEL].find(function(u) { return u.value === util; });\n"
      "        if (uObj) label = uObj.label;\n"
      "      }\n"
      "      heading.textContent = util ? ('Top ' + n + ' Rates for ' + label) : ('Top ' + n + ' Rates Right Now');\n"
      "    }\n"

        "    if (rows.length === 0) {\n"
        "      tbody.innerHTML = '<tr><td colspan=\"6\" class=\"empty-cell\">No data for that term.</td></tr>';\n"
        "      return;\n"
        "    }\n"
        "    tbody.innerHTML = rows.map(function(r, i) {\n"
        "      var calcBtn = '<button class=\"btn-calc-small\" onclick=\"window.__useInCalculator(event, ' + r.rate.toFixed(5) + ', \\'' + esc(r.supplier) + '\\')\" title=\"Select this plan for the savings calculator\">Compare</button>';\n"
        "      return '<tr>' +\n"
        "        '<td class=\"rank-cell\">' + (i + 1) + '</td>' +\n"
        "        '<td>' + esc(r.utility) + '</td>' +\n"
        "        '<td>' + esc(r.supplier) + '</td>' +\n"
        "        '<td>' + bbbPill(r.supplier, r.bbb, r.bbb_url) + '</td>' +\n"
        "        '<td>' + r.term + ' Mo</td>' +\n"
        "        '<td class=\"rate-cell\">' + r.rate.toFixed(5) + '</td>' +\n"
        "        '<td>' + calcBtn + '</td>' +\n"
        "      '</tr>';\n"
        "    }).join('');\n"
        "  }\n"
        "  // expose so the utility selector can trigger re-render after changes\n"
        "  window.__renderTopRates = render;\n"
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

    # --- 6. RATE REALITY CHECK ENGINE (supplier-focused) ---
    # The user can't change their delivery utility — but they CAN change their
    # supplier, and that's where the savings come from. This section names the
    # specific supplier offering today's best deal for each utility, and
    # compares that against the best supplier offer that was actually
    # available in the selected lookback window.
    today_dt = today_df['Date'].max()

    timeframes = {
        '6mo': 180,
        '1y': 365,
        '3y': 365*3,
        '5y': 365*5
    }

    rate_fmt = (lambda r: f"{r*100:.2f}¢/kWh") if elecHtml else (lambda r: f"${r:.2f}/MCF")

    # Exclude utility-default (PTC/SCO) rows — Rate Reality Check is about
    # switching to a competitive supplier, not staying on the default.
    market_df = filtered_df[filtered_df['Supplier'] != 'Utility'].copy()
    today_market = today_df[today_df['Supplier'] != 'Utility'].copy()

    # Term buckets — exact-match contract lengths consumers actually see offered.
    # Each term carries a different value tradeoff:
    #   6 mo  → flexibility: easy to re-shop in half a year if rates fall
    #   12 mo → balance:     the default term most consumers compare against
    #   24 mo → commitment:  locks in rate for 2 years — high reward at a low,
    #                        big regret at a premium
    TERM_OPTIONS = [1, 6, 12, 24, 36]
    TERM_VALUE_CTA = {
        1:  "Ultra-short 1-month term: maximum flexibility to switch anytime.",
        6:  "Short 6-month term: you can re-shop in 6 months if rates drop.",
        12: "Standard 12-month term: the default benchmark — balances flexibility with rate stability.",
        24: "Long 24-month term: locks in this rate for 2 full years — fantastic when locked at a low, regrettable when locked at a premium.",
        36: "Maximum 36-month term: complete rate stability for 3 full years.",
    }

    pulse_data = {}

    if not today_market.empty:
        for pid in sorted(today_market['Provider'].dropna().unique()):
            u_today_all = today_market[today_market['Provider'] == pid]
            if u_today_all.empty:
                continue

            util = u_today_all['Utility'].iloc[0]
            by_term = {}

            for term in TERM_OPTIONS:
                u_today = u_today_all[u_today_all['Term. Length'] == term]
                if u_today.empty:
                    continue

                best_idx = u_today['rate'].idxmin()
                best_today = u_today.loc[best_idx]
                today_supplier = _clean_supplier_name(best_today['Supplier'])
                today_rate = float(best_today['rate'])

                term_entry = {
                    'today_supplier': today_supplier,
                    'today_rate': rate_fmt(today_rate),
                    'today_rate_raw': today_rate,
                    'today_term': term,
                    'windows': {}
                }

                for timeframe_id, days in timeframes.items():
                    cutoff = today_dt - pd.Timedelta(days=days)
                    hist_u = market_df[(market_df['Provider'] == pid)
                                       & (market_df['Term. Length'] == term)
                                       & (market_df['Date'] >= cutoff)]
                    if len(hist_u) < 20:
                        continue

                    hist_low_idx = hist_u['rate'].idxmin()
                    hist_low_row = hist_u.loc[hist_low_idx]
                    hist_low_rate = float(hist_low_row['rate'])
                    hist_low_supplier = _clean_supplier_name(hist_low_row['Supplier'])
                    hist_low_date = hist_low_row['Date'].strftime('%b %Y')

                    premium_pct = (today_rate / hist_low_rate - 1) * 100 if hist_low_rate > 0 else 0
                    window_label = {'6mo': '6 months', '1y': 'year', '3y': '3 years', '5y': '5 years'}[timeframe_id]

                    # Status/color tier driven by premium
                    if premium_pct < 5:
                        status, color, icon = f"Near {window_label} low", "#16a34a", "🟢"
                        tier = "near_low"
                    elif premium_pct < 15:
                        status, color, icon = "Reasonable to switch", "#65a30d", "🟢"
                        tier = "reasonable"
                    elif premium_pct < 30:
                        status, color, icon = "Switching premium", "#d97706", "🟡"
                        tier = "premium"
                    else:
                        status, color, icon = "Bad time to switch", "#b91c1c", "🔴"
                        tier = "bad"

                    # CTA varies by both tier AND term — locking 24mo at a low is meaningfully different than 6mo
                    if tier == "near_low":
                        if term == 24:
                            cta = (f"Switching to {today_supplier} now locks this {window_label}-low rate "
                                   f"({rate_fmt(today_rate)}) in for a full 2 years. This is the kind of moment "
                                   f"a long-term contract pays off — you're insulated from the next price spike.")
                        elif term == 12:
                            cta = (f"Switching to {today_supplier} at {rate_fmt(today_rate)} locks today's near-low "
                                   f"rate for a year. Strong move.")
                        else:
                            cta = (f"Switching to {today_supplier} at {rate_fmt(today_rate)} captures today's "
                                   f"near-low rate, but only for 6 months. Consider 12 or 24 mo if you want to "
                                   f"keep the rate longer.")
                    elif tier == "reasonable":
                        if term == 24:
                            cta = (f"Switching to {today_supplier} works, but you're paying {premium_pct:.0f}% above "
                                   f"the past-{window_label} low ({hist_low_supplier}, {rate_fmt(hist_low_rate)} in "
                                   f"{hist_low_date}). Locking 2 years at a slight premium is a coin-flip — fine if "
                                   f"you want stability.")
                        else:
                            cta = (f"Switching to {today_supplier} at {rate_fmt(today_rate)} is decent, "
                                   f"{premium_pct:.0f}% above the {window_label} low ({hist_low_supplier} at "
                                   f"{rate_fmt(hist_low_rate)} in {hist_low_date}).")
                    elif tier == "premium":
                        if term == 24:
                            cta = (f"⚠️ Don't lock 24 months here. You'd pay {premium_pct:.0f}% above the recent low "
                                   f"({hist_low_supplier} at {rate_fmt(hist_low_rate)} in {hist_low_date}) — for "
                                   f"2 full years. If you must switch, take the 6-month so you can re-shop sooner.")
                        elif term == 12:
                            cta = (f"Switching pays {premium_pct:.0f}% above the {window_label} low "
                                   f"({hist_low_supplier} at {rate_fmt(hist_low_rate)} in {hist_low_date}). "
                                   f"Consider the 6-month term to stay flexible.")
                        else:
                            cta = (f"Switching to {today_supplier} pays {premium_pct:.0f}% above the {window_label} "
                                   f"low. 6-month limits your downside if rates fall further.")
                    else:  # bad
                        if term == 24:
                            cta = (f"🚫 Avoid a 24-month lock here. You'd be {premium_pct:.0f}% above the "
                                   f"{window_label} low ({hist_low_supplier} at {rate_fmt(hist_low_rate)} in "
                                   f"{hist_low_date}) — for two years. If your current plan still has time, wait.")
                        elif term == 12:
                            cta = (f"Switching now locks in {premium_pct:.0f}% above the {window_label} low for "
                                   f"a year. Strongly consider waiting or taking only a 6-month term.")
                        else:
                            cta = (f"Even on a 6-month term, you'd pay {premium_pct:.0f}% above the recent low. "
                                   f"Wait if your current plan allows.")

                    term_entry['windows'][timeframe_id] = {
                        'hist_low_supplier': hist_low_supplier,
                        'hist_low_rate': rate_fmt(hist_low_rate),
                        'hist_low_date': hist_low_date,
                        'premium_pct': round(premium_pct),
                        'status': status,
                        'color': color,
                        'icon': icon,
                        'cta': cta,
                    }

                if term_entry['windows']:
                    by_term[str(term)] = term_entry

            if by_term:
                pulse_data[str(pid)] = {
                    'utility': util,
                    'by_term': by_term,
                    'term_value_advice': {str(t): TERM_VALUE_CTA[t] for t in TERM_OPTIONS},
                }

    pulse_data_json = json.dumps(pulse_data)

    market_pulse_html = f"""
        <section class="card" style="padding: 0; overflow: hidden;">
            <div style="background: #f1f5f9; padding: 16px 24px; border-bottom: 1px solid var(--border);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px;">
                    <h2 style="margin: 0; font-size: 1.1em; font-weight: 800; letter-spacing: -0.02em;">Rate Reality Check — Is it a good time to switch suppliers?</h2>
                    <label style="display: flex; align-items: center; gap: 6px; font-size: 0.7em; font-weight: 700; color: var(--muted);">
                        COMPARE AGAINST:
                        <select id="pulse-timeline" style="padding: 4px 8px; border-radius: 6px; border: 1px solid var(--border); font-size: 0.75em; font-weight: 700; color: var(--text);">
                            <option value="6mo">Last 6 Months</option>
                            <option value="1y" selected>Last 1 Year</option>
                            <option value="3y">Last 3 Years</option>
                            <option value="5y">Last 5 Years</option>
                        </select>
                    </label>
                </div>
                <p style="margin: 8px 0 0; font-size: 0.85em; color: var(--muted);">
                    Your savings come from switching to a competitive <strong>supplier</strong> — not from your delivery utility. For each utility, we evaluate <strong>every contract length</strong> (6 / 12 / 24 mo) so you can see which term is the right pick right now. A 24-month lock at a low is a big win; the same lock at elevated pricing means overpaying for 2 years.
                </p>
            </div>
            <div id="market-pulse-grid" class="hero-stats" style="padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; justify-content: stretch;">
                <!-- JavaScript will populate cards here -->
            </div>
        </section>
    """ if pulse_data else ""

    pulse_js = f"""
<script>
(function() {{
    const PULSE_DATA = {pulse_data_json};
    const TERM_ORDER = ['1', '6', '12', '24', '36'];
    const grid = document.getElementById('market-pulse-grid');
    const tlSelect = document.getElementById('pulse-timeline');

    // Status tier rank (lower = better) — drives the "best pick" recommendation.
    const TIER_RANK = {{
      'Near 6 months low': 0, 'Near year low': 0, 'Near 3 years low': 0, 'Near 5 years low': 0,
      'Reasonable to switch': 1,
      'Switching premium': 2,
      'Bad time to switch': 3
    }};

    function rankTier(status) {{
      if (status && status.indexOf('Near ') === 0) return 0;
      return TIER_RANK[status] != null ? TIER_RANK[status] : 4;
    }}

    function pickBestTerm(byTerm, tf) {{
      // Score each term by (tier, then premium %). Tie-break prefers longer term
      // when within 3% premium — a longer lock at the same effective deal is better.
      const candidates = [];
      TERM_ORDER.forEach(function(t) {{
        const td = byTerm[t]; if (!td) return;
        const w = td.windows && td.windows[tf]; if (!w) return;
        candidates.push({{ term: t, tier: rankTier(w.status), premium: w.premium_pct, w: w, td: td }});
      }});
      if (!candidates.length) return null;
      candidates.sort(function(a, b) {{
        if (a.tier !== b.tier) return a.tier - b.tier;
        if (Math.abs(a.premium - b.premium) < 3) return Number(b.term) - Number(a.term); // longer term wins on near-tie
        return a.premium - b.premium;
      }});
      const best = candidates[0];
      const allBad = candidates.every(function(c) {{ return c.tier >= 3; }});
      const allPremiumOrWorse = candidates.every(function(c) {{ return c.tier >= 2; }});
      // Within-3% premiums means terms are effectively tied — the recommendation
      // is a tie-breaker, not a "this term is clearly better" call.
      const tied = candidates.length > 1 && (Math.max.apply(null, candidates.map(c => c.premium)) - Math.min.apply(null, candidates.map(c => c.premium)) < 3);
      return {{ best: best, candidates: candidates, allBad: allBad, allPremiumOrWorse: allPremiumOrWorse, tied: tied }};
    }}

    function buildRecommendationRationale(pick) {{
      // Generate a rationale that REFLECTS the comparison across all terms,
      // so we don't contradict ourselves by reusing one term's isolated CTA.
      const b = pick.best;
      const tier = b.tier;
      const supplier = b.td.today_supplier;
      const rate = b.td.today_rate;
      const term = b.term;
      const premium = b.premium;

      if (tier === 0) {{
        if (term === '24') {{
          return `Lock today's near-low rate (${{rate}}) with ${{supplier}} for a full 2 years. This is exactly the moment a long-term contract pays off.`;
        }} else if (term === '12') {{
          return `Switch to ${{supplier}} at ${{rate}}. Today's rate is near the recent low — a strong 1-year lock.`;
        }} else {{
          return `Switch to ${{supplier}} at ${{rate}} for 6 months. Near recent lows, but you'd give up the long lock — consider 12 or 24 mo if those are also near low.`;
        }}
      }}

      if (tier === 1) {{
        if (term === '24') {{
          return `${{supplier}} at ${{rate}} for 24 months. Slightly above the recent low (+${{premium}}%), but a long lock at a reasonable rate is fine for stability.`;
        }}
        return `${{supplier}} at ${{rate}} for ${{term}} months. ${{premium}}% above the recent low — a reasonable switch.`;
      }}

      if (tier === 2) {{
        if (pick.tied) {{
          return `All terms are at a similar premium (~${{premium}}%) above the recent low. If you must switch now, the ${{term}}-month with ${{supplier}} at ${{rate}} ties for the smallest premium AND locks in for the longest — best of a mediocre set. Waiting is also defensible.`;
        }}
        return `${{supplier}} at ${{rate}} for ${{term}} months is the least-bad option (+${{premium}}% above the recent low). Switching now means paying a premium — waiting is reasonable if your current plan allows.`;
      }}

      // tier 3 individual case (shouldn't usually hit here since allBad uses the other banner)
      return `${{supplier}} at ${{rate}} for ${{term}} months is the smallest premium available, but still well above the recent low (+${{premium}}%). Strongly consider waiting.`;
    }}

    function renderTermRow(t, td, w, isBest) {{
      const bg = isBest ? '#ecfdf5' : '#f8fafc';
      const border = isBest ? '#10b981' : 'transparent';
      const premiumLabel = w.premium_pct <= 0 ? 'At the low' : `+${{w.premium_pct}}% over low`;
      const bestBadge = isBest ? '<span style="background:#10b981;color:white;font-size:0.6em;font-weight:800;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:0.05em;margin-left:6px;">Best pick</span>' : '';
      return `
        <div style="background:${{bg}}; border:1px solid ${{border}}; border-radius:8px; padding:10px 12px; margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="font-weight:800; font-size:0.95em;">${{t}}-month ${{bestBadge}}</span>
            <span style="font-size:0.75em; font-weight:800; color:${{w.color}}; white-space:nowrap;">${{w.icon}} ${{w.status}}</span>
          </div>
          <div style="font-size:0.82em; color:var(--text);">
            <strong>${{td.today_supplier}}</strong> at <strong>${{td.today_rate}}</strong>
            <span style="color:${{w.color}}; font-weight:700; margin-left:4px;">${{premiumLabel}}</span>
          </div>
          <div style="font-size:0.7em; color:var(--muted); margin-top:2px;">
            Recent low: ${{w.hist_low_supplier}} at ${{w.hist_low_rate}} (${{w.hist_low_date}})
          </div>
        </div>
      `;
    }}

    function renderPulse() {{
        if (!grid) return;
        const tf = tlSelect ? tlSelect.value : '1y';
        let html = '';

        for (const [util, data] of Object.entries(PULSE_DATA)) {{
            const byTerm = data.by_term;
            if (!byTerm) continue;
            const pick = pickBestTerm(byTerm, tf);
            if (!pick) continue;

            // Headline recommendation — generated to reflect the comparison
            // across all terms, never reusing a single-term isolated CTA.
            let headline;
            if (pick.allBad) {{
              headline = `
                <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:10px 12px; margin-bottom:12px;">
                  <div style="font-size:0.75em; font-weight:800; color:#b91c1c; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px;">🚫 Don't switch right now</div>
                  <div style="font-size:0.82em; color:var(--text);">All available contract lengths are well above their recent lows. If your current plan still has time, wait.</div>
                </div>
              `;
            }} else {{
              const b = pick.best;
              const rationale = buildRecommendationRationale(pick);
              // Use neutral styling when the recommendation is a "least-bad" tie-break
              const isHighConfidence = b.tier <= 1;
              const bg = isHighConfidence ? '#ecfdf5' : '#fffbeb';
              const border = isHighConfidence ? '#10b981' : '#f59e0b';
              const titleColor = isHighConfidence ? '#047857' : '#92400e';
              const icon = isHighConfidence ? '✅' : '⚖️';
              const verb = isHighConfidence ? 'Recommended' : 'Best of available';
              headline = `
                <div style="background:${{bg}}; border:1px solid ${{border}}; border-radius:8px; padding:10px 12px; margin-bottom:12px;">
                  <div style="font-size:0.75em; font-weight:800; color:${{titleColor}}; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px;">${{icon}} ${{verb}}: ${{b.term}}-month with ${{b.td.today_supplier}}</div>
                  <div style="font-size:0.82em; color:var(--text);">${{rationale}}</div>
                </div>
              `;
            }}

            // All three term rows
            let rows = '';
            TERM_ORDER.forEach(function(t) {{
              const td = byTerm[t]; if (!td) return;
              const w = td.windows && td.windows[tf]; if (!w) return;
              const isBest = !pick.allBad && pick.best.term === t;
              rows += renderTermRow(t, td, w, isBest);
            }});

            html += `
                <div class="stat-card" data-utility="${{util}}" style="text-align:left; padding:16px;">
                    <div style="font-size:0.75em; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:10px;">If you're on ${{data.utility}}</div>
                    ${{headline}}
                    <div style="font-size:0.68em; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; margin:8px 0 6px;">All contract lengths</div>
                    ${{rows}}
                </div>
            `;
        }}
        grid.innerHTML = html || '<p style="grid-column: 1/-1; text-align: center; color: var(--muted); font-size: 0.9em; padding: 20px;">Insufficient historical data for this comparison window.</p>';
    }}

    if (tlSelect) tlSelect.addEventListener('change', renderPulse);
    renderPulse();
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
#pwa-install-banner {
  position: fixed; bottom: 20px; left: 20px; right: 20px; z-index: 2000;
  background: #1e293b; color: white; padding: 16px 20px; border-radius: 16px;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
  display: none; align-items: center; justify-content: space-between; gap: 16px;
  animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes slideUp { from { transform: translateY(100px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.pwa-content { flex: 1; font-size: 0.9em; line-height: 1.4; }
.pwa-content strong { display: block; font-size: 1.1em; margin-bottom: 2px; color: #10b981; }
.pwa-btn {
  background: #10b981; color: white; border: none; padding: 10px 18px;
  border-radius: 10px; font-weight: 700; font-size: 0.9em; cursor: pointer; white-space: nowrap;
}
.pwa-close {
  background: transparent; border: none; color: #94a3b8; font-size: 1.5em; cursor: pointer; padding: 0 4px;
}
@media (min-width: 768px) { #pwa-install-banner { max-width: 400px; left: auto; } }
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

.selection-section {
  background: white; border-bottom: 1px solid var(--border);
  margin-top: -40px; margin-bottom: 24px;
  position: relative; z-index: 5;
}
.selection-inner {
  max-width: 1100px; margin: 0 auto; padding: 28px 24px;
}
.selection-header h2 {
  margin: 0 0 8px 0; font-size: 1.5em; font-weight: 800; letter-spacing: -0.02em;
}
.selection-explainer {
  margin: 0 0 24px 0; color: var(--muted); font-size: 0.9em; line-height: 1.55;
  max-width: 780px;
}
.selection-explainer strong { color: var(--text); font-weight: 700; }
.selection-block {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 22px;
  box-shadow: var(--shadow-sm);
}
.selection-field-row {
  display: flex; flex-direction: column; gap: 8px;
  margin-bottom: 16px;
}
.selection-field-row:last-of-type { margin-bottom: 0; }
.selection-label {
  font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted); font-weight: 700;
}
.selection-field-state select {
  padding: 8px 12px; border: 1.5px solid var(--border);
  border-radius: 8px; font-size: 0.95em; font-weight: 600;
  background: white; color: var(--text); cursor: pointer;
  min-width: 180px; max-width: 220px;
}
.utility-buttons {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px; margin-top: 4px;
}
.util-btn {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 14px 16px; background: white;
  border: 1.5px solid var(--border); border-radius: 10px;
  cursor: pointer; font-family: inherit; font-size: 0.95em;
  font-weight: 600; color: var(--text); text-align: left;
  transition: all 0.15s; width: 100%;
}
.util-btn:hover {
  border-color: var(--primary); background: #eff6ff;
  transform: translateY(-1px); box-shadow: var(--shadow-sm);
}
.util-btn.util-btn-active {
  border-color: var(--primary); background: #1e40af;
  color: white;
}
.util-btn.util-btn-active .util-btn-check { color: white; }
.util-btn-check {
  font-size: 1.1em; color: var(--primary); opacity: 0;
}
.util-btn.util-btn-active .util-btn-check { opacity: 1; }
.util-btn-all {
  background: #f1f5f9; border-style: dashed;
  grid-column: 1 / -1;
}
.util-btn-all:hover { border-style: solid; }
.selection-hint {
  margin: 16px 0 0 0; color: var(--muted); font-size: 0.85em;
  font-style: italic;
}
.visually-hidden {
  position: absolute; width: 1px; height: 1px;
  overflow: hidden; clip: rect(0,0,0,0);
}
@media (max-width: 640px) {
  .selection-section { margin-top: -24px; }
  .selection-inner { padding: 20px 16px; }
  .selection-header h2 { font-size: 1.25em; }
  .utility-buttons { grid-template-columns: 1fr; }
}

.hero {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: white; padding: 60px 24px; text-align: center;
  margin-bottom: 40px;
}
.hero-content { max-width: 800px; margin: 0 auto; }
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
  margin: 40px 0 8px;
  font-size: 1.4em; font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text);
}
.section-subtitle {
  margin: 0 0 20px;
  color: var(--muted); font-size: 0.9em;
  max-width: 780px; line-height: 1.5;
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
.calculator-card {
  margin: 40px 0 0 !important;
  background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
  border: 2px solid var(--primary);
  border-radius: 24px;
}
.util-card th, .util-card td {
  padding: 10px 8px; text-align: left; font-size: 0.9em;
  border-bottom: 1px solid #f1f5f9;
}
.util-card th {
  color: var(--muted); font-weight: 600;
  font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.05em;
}
.min-rate { color: var(--accent); font-weight: 700; }

.calc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}
.calc-field { display: flex; flex-direction: column; gap: 8px; }
.calc-field label {
  font-size: 0.7em; font-weight: 800; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.calc-field input {
  padding: 12px; border: 1.5px solid var(--border);
  border-radius: 12px; font-size: 1.1em; font-weight: 600;
  transition: all 0.2s; background: white;
}
.calc-field input:focus { border-color: var(--primary); outline: none; box-shadow: 0 0 0 4px var(--primary-fade); }

.calc-result-badge {
  background: white; border-radius: 20px; padding: 24px;
  text-align: center; box-shadow: var(--shadow-sm);
  border: 1px solid var(--border); margin-top: 20px;
}
.calc-result-value { font-size: 2.8em; font-weight: 800; color: var(--accent); display: block; line-height: 1; margin: 10px 0; }
.calc-result-label { font-size: 0.95em; color: var(--muted); font-weight: 600; }

.btn-share-cool {
  background: linear-gradient(135deg, var(--primary) 0%, #1e40af 100%);
  color: white; border: none; padding: 14px 28px; border-radius: 12px;
  font-weight: 700; font-size: 1em; cursor: pointer;
  box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.3);
  transition: all 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 10px;
  margin-top: 20px; width: 100%;
}
.btn-share-cool:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4); }

.btn-calc-small {
  background: var(--primary-fade); color: var(--primary); border: 1px solid var(--primary);
  border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 0.85em;
  font-weight: 700; transition: all 0.1s; display: inline-flex; align-items: center; gap: 4px;
}
.btn-calc-small:hover { background: var(--primary); color: white; }
.btn-calc-small.selected {
  background: var(--accent); color: white; border-color: var(--accent);
}
.btn-calc-small.selected::before { content: '✓ '; }

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
        <section class="card calculator-card" id="savings-calculator" aria-label="Savings calculator">
            <h2 class="section-title" style="margin-top:0">Savings Potential</h2>
            <p class="section-subtitle">Compare your current monthly bill to the best rates in the market right now.</p>
            
            <div class="calc-grid">
                <div class="calc-field">
                    <label>What you pay now ({unit})</label>
                    <input type="number" step="0.00001" id="calc-current-rate" placeholder="e.g. {placeholder_rate}">
                </div>
                <div class="calc-field">
                    <label>Compare to rate ({unit})</label>
                    <input type="number" step="0.00001" id="calc-target-rate" placeholder="Click 'Compare' in any table">
                </div>
                <div class="calc-field">
                    <label>Monthly usage ({usage_unit_label})</label>
                    <input type="number" step="1" id="calc-usage" placeholder="e.g. {placeholder_usage}">
                </div>
                <div class="calc-field">
                    <label>Termination Fee ($, optional)</label>
                    <input type="number" step="1" id="calc-etf" value="0">
                </div>
            </div>

            <div id="calc-results-wrap" style="display:none;">
                <div class="calc-result-badge">
                    <span class="calc-result-label">Potential Annual Savings</span>
                    <span class="calc-result-value" id="calc-savings-yearly">$0.00</span>
                    <p id="calc-details" style="font-size:0.9em; color:var(--muted); margin:0;"></p>
                </div>

                <div id="calc-share-container" style="margin-top: 24px; text-align: center;">
                    <button id="btn-share" class="btn-share-cool">
                        🚀 Share My Savings
                    </button>
                </div>
            </div>
            
            <div id="calc-prompt" class="calc-result-badge" style="background:transparent; border-style:dashed;">
                <p class="calc-prompt">Enter your rate and usage above to see how much you could save.</p>
            </div>
        </section>
"""

    calculator_js = (
        "<script>\n(function() {\n"
        "  var DATA = " + calc_data_json + ";\n"
        "  var STORAGE_PREFIX = 'gAndETicker_' + DATA.dashboard_type + '_';\n"
        "  var IDS = ['calc-current-rate', 'calc-target-rate', 'calc-usage', 'calc-etf'];\n"
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
        "    return '$' + Math.abs(n).toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');\n"
        "  }\n"
        "  window.__useInCalculator = function(event, rate, supplier) {\n"
        "    var btn = event.currentTarget;\n"
        "    document.querySelectorAll('.btn-calc-small').forEach(function(b) { b.classList.remove('selected'); });\n"
        "    btn.classList.add('selected');\n"
        "    $('calc-target-rate').value = rate;\n"
        "    var label = document.querySelector('.calc-field:nth-child(2) label');\n"
        "    if (label) label.textContent = 'Comparing to ' + supplier;\n"
        "    render();\n"
        "    $('calc-target-rate').style.backgroundColor = '#fef3c7';\n"
        "    setTimeout(function() { $('calc-target-rate').style.backgroundColor = 'white'; }, 500);\n"
        "  };\n"
        "  function render() {\n"
        "    saveInputs();\n"
        "    var myRate = parseFloat($('calc-current-rate').value);\n"
        "    var targetRate = parseFloat($('calc-target-rate').value);\n"
        "    var usage = parseFloat($('calc-usage').value);\n"
        "    var etf = parseFloat($('calc-etf').value) || 0;\n"
        "    \n"
        "    if (isNaN(myRate) || isNaN(usage) || usage <= 0) {\n"
        "      $('calc-results-wrap').style.display = 'none';\n"
        "      $('calc-prompt').style.display = 'block';\n"
        "      return;\n"
        "    }\n"
        "    \n"
        "    // Default to min rate if target not set\n"
        "    if (isNaN(targetRate)) {\n"
        "      var saved = JSON.parse(localStorage.getItem('oet_selection_v1') || '{}');\n"
        "      var fuel = document.body.getAttribute('data-dashboard') || 'electric';\n"
        "      var util = saved.utilities && saved.utilities[fuel];\n"
        "      if (util && util !== 'all') {\n"
        "        targetRate = DATA.min_by_util[util];\n"
        "      }\n"
        "    }\n"
        "    \n"
        "    if (isNaN(targetRate)) {\n"
        "       $('calc-results-wrap').style.display = 'none';\n"
        "       $('calc-prompt').style.display = 'block';\n"
        "       return;\n"
        "    }\n"
        "    \n"
        "    $('calc-results-wrap').style.display = 'block';\n"
        "    $('calc-prompt').style.display = 'none';\n"
        "    \n"
        "    var monthlyDiff = (myRate - targetRate) * usage;\n"
        "    var yearlyDiff = monthlyDiff * 12;\n"
        "    \n"
        "    $('calc-savings-yearly').textContent = (yearlyDiff >= 0 ? '' : '-') + fmtMoney(yearlyDiff);\n"
        "    $('calc-savings-yearly').style.color = yearlyDiff >= 0 ? 'var(--accent)' : 'var(--warn)';\n"
        "    \n"
        "    var detailText = 'That is ' + fmtMoney(monthlyDiff) + ' per month savings';\n"
        "    if (etf > 0 && monthlyDiff > 0) {\n"
        "      var be = Math.ceil(etf / monthlyDiff);\n"
        "      detailText += '. Breaks even on your ' + fmtMoney(etf) + ' fee in ' + be + ' months.';\n"
        "    }\n"
        "    $('calc-details').textContent = detailText;\n"
        "  }\n"
        "  document.addEventListener('DOMContentLoaded', function() {\n"
        "    loadInputs();\n"
        "    IDS.forEach(function(id) {\n"
        "      var el = $(id);\n"
        "      el.addEventListener('input', render);\n"
        "    });\n"
        "\n"
        "    // Share Logic\n"
        "    $('btn-share').addEventListener('click', function() {\n"
        "      var myRate = parseFloat($('calc-current-rate').value);\n"
        "      var targetRate = parseFloat($('calc-target-rate').value);\n"
        "      var usage = parseFloat($('calc-usage').value);\n"
        "      var yearlyDiff = (myRate - targetRate) * usage * 12;\n"
        "      \n"
        "      var fuelEmoji = DATA.dashboard_type === 'electric' ? '⚡' : '🔥';\n"
        "      var msg = fuelEmoji + ' I just found ' + fmtMoney(yearlyDiff) + '/year in energy savings using RateSavvy!\\n\\nCheck your own rates at: ' + window.location.href;\n"
        "      \n"
        "      if (navigator.share) {\n"
        "        navigator.share({ title: 'RateSavvy Savings', text: msg, url: window.location.href }).catch(function(e) { console.error('Error sharing:', e); });\n"
        "      } else {\n"
        "        navigator.clipboard.writeText(msg).then(function() {\n"
        "          var originalText = $('btn-share').innerHTML;\n"
        "          $('btn-share').innerHTML = '✅ Copied to Clipboard!';\n"
        "          setTimeout(function() { $('btn-share').innerHTML = originalText; }, 2000);\n"
        "        });\n"
        "      }\n"
        "    });\n"
        "\n"
        "    render();\n"
        "    // Re-render when utility changes to update the default targetRate if needed\n"
        "    document.getElementById('utility-select').addEventListener('change', render);\n"
        "  });\n"
        "})();\n</script>"
    )

    elec_active = 'tab-active' if elecHtml else ''
    gas_active = 'tab-active' if not elecHtml else ''
    dash_type = 'electric' if elecHtml else 'gas'

    # Build the state dropdown from STATE_CONFIG, marking the current state
    # selected and embedding each state's electric/gas filename as data
    # attributes so the client-side JS can navigate on change.
    state_options = "\n".join(
        f'<option value="{code}" data-elec="{cfg["elec_file"]}" data-gas="{cfg["gas_file"]}"'
        f'{" selected" if code == state else ""}>{cfg["name"]}</option>'
        for code, cfg in STATE_CONFIG.items()
    )

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
    
    # Prepare JS utility objects for the state selector
    state_util_map = providers.for_state(state)
    js_utilities = {
        'electric': [{'value': str(k), 'label': v} for k, v in state_util_map['elec'].items()],
        'gas': [{'value': str(k), 'label': v} for k, v in state_util_map['gas'].items()]
    }
    js_utilities_json = json.dumps(js_utilities)

    full_html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{dashboard_title} · RateSavvy</title>
    <meta property="og:title" content="{dashboard_title} · RateSavvy">
    <meta property="og:description" content="Daily energy rate tracking for deregulated US markets. Find the best supplier in your state.">
    <meta property="og:type" content="website">
    <meta name="description" content="RateSavvy — find the best energy supplier in your state. Daily rate tracking for deregulated US markets, starting with Ohio.">
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
      var UTILITIES = {js_utilities_json};
    </script>
    <div id="pwa-install-banner">
      <div class="pwa-content" id="pwa-message">
        <strong>Install RateSavvy</strong>
        Add to your home screen for quick access to latest rates.
      </div>
      <button class="pwa-btn" id="pwa-install-btn">Install</button>
      <button class="pwa-close" id="pwa-close-btn">&times;</button>
    </div>

    <script>
    (function() {{
      var deferredPrompt;
      var banner = document.getElementById('pwa-install-banner');
      var installBtn = document.getElementById('pwa-install-btn');
      var closeBtn = document.getElementById('pwa-close-btn');
      var message = document.getElementById('pwa-message');

      var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
      var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
      var dismissKey = 'pwa_dismissed_v1';
      var dismissedAt = localStorage.getItem(dismissKey);
      var recentlyDismissed = dismissedAt && (Date.now() - parseInt(dismissedAt) < 7 * 24 * 60 * 60 * 1000);

      function showBanner() {{
        if (isStandalone || recentlyDismissed) return;
        
        if (isIOS) {{
          message.innerHTML = '<strong>Install RateSavvy</strong>Tap the "Share" icon and select "Add to Home Screen"';
          installBtn.style.display = 'none';
          banner.style.display = 'flex';
        }} else {{
          window.addEventListener('beforeinstallprompt', (e) => {{
            e.preventDefault();
            deferredPrompt = e;
            banner.style.display = 'flex';
          }});
        }}
      }}

      installBtn.addEventListener('click', () => {{
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choice) => {{
          if (choice.outcome === 'accepted') banner.style.display = 'none';
          deferredPrompt = null;
        }});
      }});

      closeBtn.addEventListener('click', () => {{
        banner.style.display = 'none';
        localStorage.setItem(dismissKey, Date.now().toString());
      }});

      showBanner();
    }})();

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
    <span class="brand"><a href="index.html" style="color:inherit;text-decoration:none;">RateSavvy</a></span>
    <div class="tabs">
    <a href="electric_dashboard.html" id="tab-link-electric" class="tab {elec_active}" data-tab="electric">Electric</a>
    <a href="gas_dashboard.html" id="tab-link-gas" class="tab {gas_active}" data-tab="gas">Gas</a>
    </div>
    </div>
    </nav>
    {hero_section}
    <section class="selection-section" id="selection-bar">
      <div class="selection-inner">
        <div class="selection-header">
          <h2>Who delivers your {dash_type}?</h2>
          <p class="selection-explainer">
            Your <strong>utility company</strong> (also called the <strong>delivery company</strong>) is who runs the
            wires or pipes down your street and reads your meter — they're responsible for the lines, outages, and getting
            power to your home. <strong>They don't have to generate the power</strong>: deregulated states like yours let you pick a different
            supplier for the actual energy, which is where you can save money. Pick yours below to see rates tailored to your area.
          </p>
        </div>

        <div class="selection-block">
          <div class="selection-field-row">
            <label class="selection-field selection-field-state">
              <span class="selection-label">State</span>
              <select id="state-select">
                {state_options}
              </select>
            </label>
          </div>
          <div class="selection-field-row">
            <span class="selection-label">Your utility / delivery company</span>
            <div class="utility-buttons" id="utility-buttons"></div>
            <select id="utility-select" data-fuel="{dash_type}" class="visually-hidden"></select>
          </div>
          <p class="selection-hint" id="selection-hint"></p>
        </div>
      </div>
    </section>
    <main class="container">
    <p style="margin-top: -24px; margin-bottom: 32px; font-size: 0.85em; font-style: italic; color: #94a3b8; text-align: center;">
    * This is a free open-source project. Rates are automated and may contain errors. Always verify data on official provider websites.
    </p>
    {top_rates_section_html}
    {market_pulse_html}
    {calculator_html}
    <h2 class="section-title">Available Plans by Delivery Utility</h2>
    <p class="section-subtitle">Every supplier currently offering plans through each delivery utility in your area, sorted by rate. The lowest rate for each provider is highlighted.</p>
    <div class="leaderboard-cards">
    {"".join(table_sections)}
    </div>
    <details class="chart-section">
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
    <script>
    (function() {{
      var STORAGE_KEY = 'oet_selection_v1';
      var FUEL = document.body.getAttribute('data-dashboard') || 'electric';

      function loadSelection() {{
        try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }}
        catch (e) {{ return {{}}; }}
      }}
      function saveSelection(sel) {{
        try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(sel)); }} catch (e) {{}}
      }}

      // Populate utility buttons + hidden select for this fuel
      var utilSel = document.getElementById('utility-select');
      var utilButtons = document.getElementById('utility-buttons');
      var stateSel = document.getElementById('state-select');
      var hint = document.getElementById('selection-hint');

      var opts = '<option value="">— Pick yours —</option>';
      var btnHtml = '';
      UTILITIES[FUEL].forEach(function(u) {{
        opts += '<option value="' + u.value + '">' + u.label + '</option>';
        btnHtml += '<button type="button" class="util-btn" data-value="' + u.value + '">' +
                     '<span>' + u.label + '</span>' +
                     '<span class="util-btn-check">✓</span>' +
                   '</button>';
      }});
      opts += '<option value="all">Compare all ' + FUEL + ' options in your state</option>';
      btnHtml += '<button type="button" class="util-btn util-btn-all" data-value="all">' +
                   '<span>Compare all ' + FUEL + ' options in your state</span>' +
                   '<span class="util-btn-check">✓</span>' +
                 '</button>';
      utilSel.innerHTML = opts;
      utilButtons.innerHTML = btnHtml;

      // Load saved selection
      var saved = loadSelection();
      if (saved.state) {{
        stateSel.value = saved.state;
        var opt = stateSel.options[stateSel.selectedIndex];
        if (opt) {{
          var target = FUEL === 'gas' ? opt.getAttribute('data-gas') : opt.getAttribute('data-elec');
          var current = window.location.pathname.split('/').pop() || 'index.html';
          if (target && target !== current && (current.indexOf('dashboard') !== -1)) {{
            window.location.replace(target);
            return;
          }}
        }}
      }}
      var savedUtil = (saved.utilities && saved.utilities[FUEL]) || '';
      if (savedUtil) utilSel.value = savedUtil;

      function updateTabLinks() {{
        var opt = stateSel.options[stateSel.selectedIndex];
        if (!opt) return;
        var elecFile = opt.getAttribute('data-elec');
        var gasFile = opt.getAttribute('data-gas');
        var elecTab = document.getElementById('tab-link-electric');
        var gasTab = document.getElementById('tab-link-gas');
        if (elecTab && elecFile) elecTab.href = elecFile;
        if (gasTab && gasFile) gasTab.href = gasFile;
      }}
      updateTabLinks();

      function updateActiveButton(value) {{
        utilButtons.querySelectorAll('.util-btn').forEach(function(b) {{
          b.classList.toggle('util-btn-active', b.dataset.value === value);
        }});
      }}
      updateActiveButton(utilSel.value);

      function applyFilter(utility) {{
        // Reset: show everything
        document.querySelectorAll('[data-utility]').forEach(function(el) {{
          el.style.display = '';
        }});

        if (!utility) {{
          hint.textContent = '';
          return;
        }}
        if (utility === 'all') {{
          hint.textContent = 'Showing all utilities';
          return;
        }}

        // Hide non-matching elements
        document.querySelectorAll('[data-utility]').forEach(function(el) {{
          if (el.dataset.utility !== utility) {{
            el.style.display = 'none';
          }}
        }});
        hint.textContent = 'Filtered to your utility';

        // Pre-select calculator utility dropdown
        var calcSel = document.getElementById('calc-utility');
        if (calcSel) {{
          for (var i = 0; i < calcSel.options.length; i++) {{
            if (calcSel.options[i].value === utility) {{
              calcSel.value = utility;
              calcSel.dispatchEvent(new Event('change'));
              break;
            }}
          }}
        }}
      }}

      applyFilter(utilSel.value);

      // Async-rendered sections (pulse cards, top-rates rows) need re-filter after they mount
      function filterDynamic() {{
        var u = utilSel.value;
        if (!u || u === 'all') return;
        document.querySelectorAll('[data-utility]').forEach(function(el) {{
          if (el.dataset.utility !== u) el.style.display = 'none';
        }});
      }}
      ['market-pulse-grid'].forEach(function(id) {{
        var node = document.getElementById(id);
        if (node) new MutationObserver(filterDynamic).observe(node, {{ childList: true }});
      }});

      // Save + apply on change
      utilSel.addEventListener('change', function() {{
        var sel = loadSelection();
        sel.state = stateSel.value || 'OH';
        sel.utilities = sel.utilities || {{}};
        sel.utilities[FUEL] = utilSel.value;
        saveSelection(sel);
        applyFilter(utilSel.value);
        updateActiveButton(utilSel.value);
        // Top Rates table re-renders from the per-utility bucket
        if (typeof window.__renderTopRates === 'function') window.__renderTopRates();
      }});

      utilButtons.addEventListener('click', function(e) {{
        var btn = e.target.closest('.util-btn');
        if (!btn) return;
        utilSel.value = btn.dataset.value;
        utilSel.dispatchEvent(new Event('change'));
      }});
      stateSel.addEventListener('change', function() {{
        var sel = loadSelection();
        sel.state = stateSel.value;
        saveSelection(sel);
        updateTabLinks();
        // If this state has a different dashboard file for the current fuel,
        // navigate to it. (Once we have more than one state in STATE_CONFIG,
        // each option carries data-elec / data-gas attributes pointing at
        // that state's electric/gas dashboards.)
        var opt = stateSel.options[stateSel.selectedIndex];
        var target = FUEL === 'gas' ? opt.getAttribute('data-gas') : opt.getAttribute('data-elec');
        if (target && target !== window.location.pathname.split('/').pop()) {{
          window.location.href = target;
        }}
      }});
    }})();
    </script>
    </body>
    </html>
    """
    with open(html_file_name, 'w', encoding='utf-8') as f:
        f.write(full_html)
# --- EXECUTION ---
# Iterates over every state present in the parquet and emits its electric
# + gas dashboards. Ohio keeps the legacy filenames (electric_dashboard.html /
# gas_dashboard.html) so existing URLs and the GitHub Pages config don't
# break; additional states get prefixed filenames (e.g. pa-electric_dashboard.html).
data_file = 'allData.parquet'

# Per-state filename + threshold config. As we onboard more states, add an
# entry here. Filenames intentionally collide with the legacy URLs for OH.
STATE_CONFIG = {
    'OH': {
        'name': 'Ohio',
        'elec_file': 'electric_dashboard.html',
        'gas_file': 'gas_dashboard.html',
        'elec_threshold': 0.0869,
        'gas_threshold': 2.99,
    },
    'PA': {
        'name': 'Pennsylvania',
        'elec_file': 'pa-electric_dashboard.html',
        'gas_file':  'pa-gas_dashboard.html',
        'elec_threshold': 0.09,
        'gas_threshold':  3.00,
    },
    'IL': {
        'name': 'Illinois',
        'elec_file': 'il-electric_dashboard.html',
        'gas_file':  'il-gas_dashboard.html',
        'elec_threshold': 0.09,   # ComEd PTC has been ~9–11 cents/kWh
        'gas_threshold':  5.00,   # IL gas PTC ~$0.36/therm × 10.37 ≈ $3.73/Mcf; cushion above
    },
}


def _states_in_data(path):
    """Return the list of state codes that actually have rows in the parquet."""
    df = pd.read_parquet(path)
    if 'state' not in df.columns:
        return ['OH']
    return sorted(s for s in df['state'].dropna().unique() if s in STATE_CONFIG)


for _state in _states_in_data(data_file):
    cfg = STATE_CONFIG[_state]
    generate_energy_dashboard(
        file_path=data_file,
        html_file_name=cfg['elec_file'],
        elecHtml=True,
        top_link_url=cfg['gas_file'],
        top_link_text='Switch to Gas Dashboard',
        threshold_rate=cfg['elec_threshold'],
        state=_state,
    )
    generate_energy_dashboard(
        file_path=data_file,
        html_file_name=cfg['gas_file'],
        elecHtml=False,
        top_link_url=cfg['elec_file'],
        top_link_text='Switch to Electric Dashboard',
        threshold_rate=cfg['gas_threshold'],
        state=_state,
    )
