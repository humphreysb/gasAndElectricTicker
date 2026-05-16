import json
from pathlib import Path

def fix():
    with open('build_dashboard.py', 'r') as f:
        lines = f.readlines()

    start_idx = 0
    for i, line in enumerate(lines):
        if 'hero_section = f"""' in line:
            start_idx = i
            break
    
    if start_idx == 0:
        print("Could not find hero_section")
        return

    head = lines[:start_idx]
    
    # We need to define AGGREGATION_RATES and other things that might be used
    # Wait, I already added them to the head.
    
    tail = """    hero_section = f\"\"\"
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
    \"\"\"

    # --- Savings calculator data + UI ---
    usage_unit_label = "kWh" if elecHtml else "MCF"
    placeholder_rate = "0.10" if elecHtml else "5.00"
    placeholder_usage = "900" if elecHtml else "10"

    # Prepare aggregation data for this specific dashboard type
    dash_category = "Electric" if elecHtml else "Gas"
    agg_filtered = {}
    for city, services in AGGREGATION_RATES.items():
        if dash_category in services:
            agg_filtered[city] = services[dash_category]

    calc_data = {
        'unit': unit,
        'usage_unit': usage_unit_label,
        'dashboard_type': 'electric' if elecHtml else 'gas',
        'min_by_util': current_min_by_util,
        'latest_date': current_date_str,
        'aggregation': agg_filtered
    }
    calc_data_json = json.dumps(calc_data)

    util_options = "\\n".join(
        f'<option value="{u}">{u}</option>' for u in sorted(current_min_by_util.keys())
    )
    
    # Prepare city options for the aggregation comparison
    city_options = "\\n".join(
        f'<option value="{c}">{c}</option>' for c in sorted(agg_filtered.keys())
    )

    calculator_html = f\"\"\"
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
                <label>Compare with my city (Optional)
                    <select id="calc-city">
                        <option value="">— none (private rate) —</option>
                        {city_options}
                    </select>
                </label>
                <label>Early termination fee ($, optional)
                    <input type="number" step="1" id="calc-etf" value="0">
                </label>
            </div>
            <div class="calc-results" id="calc-results">
                <p class="calc-prompt">Enter your details above to see savings.</p>
            </div>
        </section>
\"\"\"

    calculator_js = (
        "<script>\\n(function() {\\n"
        "  var DATA = " + calc_data_json + ";\\n"
        "  var STORAGE_PREFIX = 'gAndETicker_' + DATA.dashboard_type + '_';\\n"
        "  var IDS = ['calc-utility', 'calc-current-rate', 'calc-usage', 'calc-etf', 'calc-city'];\\n"
        "  function $(id) { return document.getElementById(id); }\\n"
        "  function loadInputs() {\\n"
        "    IDS.forEach(function(id) {\\n"
        "      var saved = localStorage.getItem(STORAGE_PREFIX + id);\\n"
        "      if (saved !== null) $(id).value = saved;\\n"
        "    });\\n"
        "  }\\n"
        "  function saveInputs() {\\n"
        "    IDS.forEach(function(id) {\\n"
        "      localStorage.setItem(STORAGE_PREFIX + id, $(id).value);\\n"
        "    });\\n"
        "  }\\n"
        "  function fmtMoney(n) {\\n"
        "    return '$' + n.toFixed(2).replace(/\\\\B(?=(\\\\d{3})+(?!\\\\d))/g, ',');\\n"
        "  }\\n"
        "  function render() {\\n"
        "    saveInputs();\\n"
        "    var util = $('calc-utility').value;\\n"
        "    var myRate = parseFloat($('calc-current-rate').value);\\n"
        "    var usage = parseFloat($('calc-usage').value);\\n"
        "    var city = $('calc-city').value;\\n"
        "    var etf = parseFloat($('calc-etf').value) || 0;\\n"
        "    var results = $('calc-results');\\n"
        "\\n"
        "    if (isNaN(usage) || usage <= 0) {\\n"
        "      results.innerHTML = '<p class=\\\"calc-prompt\\\">Enter your monthly usage to see savings.</p>';\\n"
        "      return;\\n"
        "    }\\n"
        "\\n"
        "    var compareRate = myRate;\\n"
        "    var compareLabel = 'your current rate';\\n"
        "\\n"
        "    if (city && DATA.aggregation[city]) {\\n"
        "      // Use the first aggregation rate found for this city as the \\'my rate\\' baseline\\n"
        "      var cityData = DATA.aggregation[city][0];\\n"
        "      compareRate = cityData.rate;\\n"
        "      compareLabel = 'the ' + city + ' aggregation rate (' + cityData.label + ')';\\n"
        "      $('calc-current-rate').disabled = true;\\n"
        "      $('calc-current-rate').value = compareRate;\\n"
        "    } else {\\n"
        "      $('calc-current-rate').disabled = false;\\n"
        "    }\\n"
        "\\n"
        "    if (!util || isNaN(compareRate)) {\\n"
        "      results.innerHTML = '<p class=\\\"calc-prompt\\\">Pick a utility' + (city ? '' : ' and enter your rate') + ' to see savings.</p>';\\n"
        "      return;\\n"
        "    }\\n"
        "\\n"
        "    var minRate = DATA.min_by_util[util];\\n"
        "    if (minRate === undefined) {\\n"
        "      results.innerHTML = '<p class=\\\"calc-prompt\\\">No current rate data for ' + util + '.</p>';\\n"
        "      return;\\n"
        "    }\\n"
        "\\n"
        "    var monthlyDiff = (compareRate - minRate) * usage;\\n"
        "    var yearlyDiff = monthlyDiff * 12;\\n"
        "    var html = '';\\n"
        "    html += '<p style=\\\"margin:0 0 12px;color:#555;font-size:0.95em;\\\">Comparing <b>' + compareLabel + '</b> (<b>' + compareRate.toFixed(5) + ' ' + DATA.unit + '</b>) against ' + util + \\'s current daily minimum of <b>\\' + minRate.toFixed(5) + \\' \\' + DATA.unit + \\'</b>.</p>\\';\\n"
        "    if (monthlyDiff <= 0) {\\n"
        "      html += '<p class=\\\"calc-neutral\\\">The market is currently higher than ' + (city ? 'your city rate' : 'your rate') + '. No switch needed.</p>';\\n"
        "    } else {\\n"
        "      html += '<p class=\\\"calc-win\\\">Switching to the market leader could save you:</p><ul>';\\n"
        "      html += '<li>' + fmtMoney(monthlyDiff) + ' / month</li>';\\n"
        "      html += '<li>' + fmtMoney(yearlyDiff) + ' / year</li>';\\n"
        "      if (etf > 0) {\\n"
        "        var be = Math.ceil(etf / monthlyDiff);\\n"
        "        html += '<li>Breakeven on ' + fmtMoney(etf) + ' early-termination fee: <b>' + be + ' month' + (be === 1 ? '' : 's') + '</b></li>';\\n"
        "      }\\n"
        "      html += '</ul>';\\n"
        "    }\\n"
        "    results.innerHTML = html;\\n"
        "  }\\n"
        "  document.addEventListener(\\'DOMContentLoaded\\', function() {\\n"
        "    loadInputs();\\n"
        "    IDS.forEach(function(id) {\\n"
        "      var el = $(id);\\n"
        "      el.addEventListener(\\'input\\', render);\\n"
        "      el.addEventListener(\\'change\\', function() {\\n"
        "        if (id === \\'calc-utility\\') updateMapHighlight(el.value);\\n"
        "        render();\\n"
        "      });\\n"
        "    });\\n"
        "\\n"
        "    // Map Interaction Logic\\n"
        "    var regions = document.querySelectorAll(\\'.map-region\\');\\n"
        "    var utilSelect = $(\\'calc-utility\\');\\n"
        "\\n"
        "    function updateMapHighlight(selectedUtil) {\\n"
        "      regions.forEach(function(r) {\\n"
        "        var title = r.getAttribute(\\'title\\');\\n"
        "        // Handle fuzzy matching for AEP/AES brands\\n"
        "        var isMatch = selectedUtil.includes(title) || title.includes(selectedUtil);\\n"
        "        r.classList.toggle(\\'active\\', isMatch);\\n"
        "      });\\n"
        "    }\\n"
        "\\n"
        "    regions.forEach(function(region) {\\n"
        "      region.addEventListener(\\'click\\', function() {\\n"
        "        var targetUtil = region.getAttribute(\\'title\\');\\n"
        "        // Find the matching option in the dropdown\\n"
        "        for (var i = 0; i < utilSelect.options.length; i++) {\\n"
        "          var opt = utilSelect.options[i].value;\\n"
        "          if (opt.includes(targetUtil) || targetUtil.includes(opt)) {\\n"
        "            utilSelect.value = opt;\\n"
        "            updateMapHighlight(opt);\\n"
        "            render();\\n"
        "            break;\\n"
        "          }\\n"
        "        }\\n"
        "      });\\n"
        "    });\\n"
        "\\n"
        "    // Initial Map State\\n"
        "    updateMapHighlight(utilSelect.value);\\n"
        "    render();\\n"
        "  });\\n"
        "})();\\n</script>"
    )

    elec_active = 'tab-active' if elecHtml else ''
    gas_active = 'tab-active' if not elecHtml else ''
    dash_type = 'electric' if elecHtml else 'gas'

    weather_js = (
        "<script>\\n(function() {\\n"
        "  var LAT = 39.96, LON = -82.99;\\n"  # Columbus, Ohio
        "  var CACHE_KEY = 'gAndETicker_weather_v1';\\n"
        "  var CACHE_TTL_MS = 12 * 60 * 60 * 1000;\\n"
        "  function loadCache() {\\n"
        "    try {\\n"
        "      var raw = localStorage.getItem(CACHE_KEY);\\n"
        "      if (!raw) return null;\\n"
        "      var obj = JSON.parse(raw);\\n"
        "      if (Date.now() - obj.ts > CACHE_TTL_MS) return null;\\n"
        "      return obj.data;\\n"
        "    } catch (e) { return null; }\\n"
        "  }\\n"
        "  function saveCache(data) {\\n"
        "    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ts: Date.now(), data: data})); } catch (e) {}\\n"
        "  }\\n"
        "  function fetchWeather() {\\n"
        "    var cached = loadCache();\\n"
        "    if (cached) return Promise.resolve(cached);\\n"
        "    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + LAT + '&longitude=' + LON +\\n"
        "      '&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min&past_days=92&forecast_days=14' +\\n"
        "      '&temperature_unit=fahrenheit&timezone=America%2FNew_York';\\n"
        "    return fetch(url).then(function(r) { if (!r.ok) throw new Error('open-meteo ' + r.status); return r.json(); })\\n"
        "      .then(function(data) { saveCache(data); return data; });\\n"
        "  }\\n"
        "  function findWeatherChart() {\\n"
        "    var views = document.querySelectorAll('.chart-view[data-view=\"weather\"] .js-plotly-plot');\\n"
        "    return views[0] || null;\\n"
        "  }\\n"
        "  function applyOverlay(chartDiv, wx) {\\n"
        "    if (!chartDiv || !window.Plotly || !wx || !wx.daily) return;\\n"
        "    var dates = wx.daily.time;\\n"
        "    var tMean = wx.daily.temperature_2m_mean;\\n"
        "    var tMax = wx.daily.temperature_2m_max;\\n"
        "    var tMin = wx.daily.temperature_2m_min;\\n"
        "    var today = new Date().toISOString().slice(0, 10);\\n"
        "    var splitIdx = dates.findIndex(function(d) { return d > today; });\\n"
        "    if (splitIdx < 0) splitIdx = dates.length;\\n"
        "    var histX = dates.slice(0, splitIdx);\\n"
        "    var histY = tMean.slice(0, splitIdx);\\n"
        "    var fcX = dates.slice(Math.max(splitIdx - 1, 0));\\n"
        "    var fcY = tMean.slice(Math.max(splitIdx - 1, 0));\\n"
        "    var bandX = dates.concat([].slice.call(dates).reverse());\\n"
        "    var bandY = tMax.concat([].slice.call(tMin).reverse());\\n"
        "    var traces = [\\n"
        "      { x: bandX, y: bandY, fill: 'toself', fillcolor: 'rgba(59, 130, 246, 0.08)',\\n"
        "        line: {color: 'rgba(0,0,0,0)'}, name: 'Temp range (min/max)', yaxis: 'y2',\\n"
        "        hoverinfo: 'skip', showlegend: true, type: 'scatter' },\\n"
        "      { x: histX, y: histY, mode: 'lines', name: 'Temp mean (°F)', yaxis: 'y2',\\n"
        "        line: {color: '#3b82f6', width: 2}, type: 'scatter' },\\n"
        "      { x: fcX, y: fcY, mode: 'lines', name: 'Temp forecast', yaxis: 'y2',\\n"
        "        line: {color: '#3b82f6', width: 2, dash: 'dot'}, type: 'scatter' }\\n"
        "    ];\\n"
        "    Plotly.addTraces(chartDiv, traces);\\n"
        "    Plotly.relayout(chartDiv, {\\n"
        "      shapes: [{ type: 'line', x0: today, x1: today, yref: 'paper', y0: 0, y1: 1,\\n"
        "                 line: {color: '#9ca3af', width: 1, dash: 'dash'} }],\\n"
        "      annotations: [{ x: today, y: 1, yref: 'paper', text: 'today', showarrow: false,\\n"
        "                      yanchor: 'bottom', font: {size: 10, color: '#9ca3af'} }]\\n"
        "    });\\n"
        "  }\\n"
        "  function init() {\\n"
        "    var chartDiv = findWeatherChart();\\n"
        "    if (!chartDiv) return;\\n"
        "    if (chartDiv.dataset.weatherLoaded === '1') return;\\n"
        "    chartDiv.dataset.weatherLoaded = '1';\\n"
        "    fetchWeather().then(function(wx) { applyOverlay(chartDiv, wx); })\\n"
        "      .catch(function(err) { console.warn('Weather overlay unavailable:', err); chartDiv.dataset.weatherLoaded = '0'; });\\n"
        "  }\\n"
        "  if (document.readyState === 'loading') {\\n"
        "    document.addEventListener('DOMContentLoaded', init);\\n"
        "  } else {\\n"
        "    init();\\n"
        "  }\\n"
        "})();\\n</script>"
    )

    chart_switcher_js = (
        "<script>\\n(function() {\\n"
        "  var DASH = document.body.getAttribute('data-dashboard') || 'x';\\n"
        "  function bind(selectId, viewAttr, viewClass) {\\n"
        "    var sel = document.getElementById(selectId);\\n"
        "    if (!sel) return;\\n"
        "    var KEY = 'gAndETicker_' + selectId + '_' + DASH;\\n"
        "    function showView(target) {\\n"
        "      document.querySelectorAll('.' + viewClass).forEach(function(div) {\\n"
        "        var match = div.getAttribute(viewAttr) === target;\\n"
        "        div.hidden = !match;\\n"
        "        if (match) {\\n"
        "          var plot = div.querySelector('.js-plotly-plot');\\n"
        "          if (plot && window.Plotly) {\\n"
        "            setTimeout(function() { Plotly.Plots.resize(plot); }, 0);\\n"
        "          }\\n"
        "        }\\n"
        "      });\\n"
        "    }\\n"
        "    var saved = localStorage.getItem(KEY);\\n"
        "    if (saved && [].some.call(sel.options, function(o) { return o.value === saved; })) {\\n"
        "      sel.value = saved;\\n"
        "      showView(saved);\\n"
        "    }\\n"
        "    sel.addEventListener('change', function() {\\n"
        "      localStorage.setItem(KEY, sel.value);\\n"
        "      showView(sel.value);\\n"
        "    });\\n"
        "  }\\n"
        "  bind('chart-view-select', 'data-view', 'chart-view');\\n"
        "  bind('trends-view-select', 'data-trend', 'trend-view');\\n"
        "})();\\n</script>"
    )

    map_html = f\"\"\"
        <div class="ohio-map-box">
            <span style="font-size: 0.7em; font-weight: 700; color: var(--muted); text-transform: uppercase; margin-bottom: 12px;">Quick Select Your Region</span>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" class="ohio-map">
              <path d="M120 40 L380 40 L440 100 L440 400 L250 460 L60 400 L60 100 Z" fill="none" stroke="#e2e8f0" stroke-width="2"/>
              <path d="M60 100 L200 100 L200 180 L60 180 Z" class="map-region" data-provider="3" title="Toledo Edison"/>
              <path d="M300 40 L440 100 L440 150 L300 150 Z" class="map-region" data-provider="6" title="The Illuminating Co"/>
              <path d="M200 100 L300 40 L300 150 L440 150 L440 250 L320 250 L320 180 L200 180 Z" class="map-region" data-provider="7" title="Ohio Edison"/>
              <path d="M60 180 L200 180 L200 320 L60 320 Z" class="map-region" data-provider="9" title="AES Ohio"/>
              <path d="M60 320 L200 320 L200 420 L120 450 L60 400 Z" class="map-region" data-provider="4" title="Duke Energy"/>
              <path d="M200 180 L320 180 L320 250 L440 250 L440 400 L250 460 L200 420 Z" class="map-region" data-provider="2" title="AEP Ohio"/>
              <text x="130" y="140" class="map-label">Toledo</text>
              <text x="370" y="100" class="map-label">Cleveland</text>
              <text x="260" y="240" class="map-label">Columbus</text>
              <text x="130" y="250" class="map-label">Dayton</text>
              <text x="130" y="380" class="map-label">Cincy</text>
            </svg>
            <p style="font-size: 0.65em; color: var(--muted); margin-top: 12px; text-align: center;">Click your region to filter rates</p>
        </div>
    \"\"\"

    full_html = f\"\"\"<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Ohio {dashboard_title}</title>
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
        
        <div class="map-container">
            {map_html}
            {calculator_html}
        </div>
        
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
</body>
</html>
\"\"\"
    
    with open(html_file_name, 'w', encoding='utf-8') as f:
        f.write(full_html)

fix()
