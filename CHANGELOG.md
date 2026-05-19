# Changelog

Notable changes to RateSavvy. Newest at the top.

## Unreleased

### Added
- **Pennsylvania support.** Second state online. Scraper pulls residential rates from PAPowerSwitch (electric: PECO, PPL, Duquesne, Met-Ed, Penelec, Penn Power, West Penn Power, UGI) and PAGasSwitch (gas: UGI, Columbia Gas of PA, PECO Gas, Peoples, National Fuel, PGW). Daily run now emits `pa-electric_dashboard.html` and `pa-gas_dashboard.html` alongside the Ohio dashboards.
- **Multi-state architecture.** `allData.parquet` carries a `state` column. `providers.py` is a state-keyed registry with `for_state(code)` lookup. Per-state scrapers live under `scrapers/`. `energy_scraper.py` is now a dispatcher that runs each registered scraper, isolating failures so one state's outage doesn't stop the rest. `STATE_CONFIG` in `build_dashboard.py` makes adding state #3 a four-line change.
- **Test harness** (`tests/`). 14 unittest checks covering the scraper interface contract and the parquet schema. Runs in <1 second, no network calls, no new dependencies. Wired into the daily workflow as a pre-flight check and a post-scrape verification.
- **Rate Reality Check.** Per-utility card lists all three contract lengths (6 / 12 / 24 mo) side-by-side. Each card shows today's best supplier + rate + premium vs. the historical low. A top-of-card banner picks the recommended term, generated separately from the per-term rows so the recommendation never contradicts the row it endorses. Status banner styling adapts: green "✅ Recommended" when a term is at or near a recent low, amber "⚖️ Best of available" when every term is at a similar premium and the recommendation is a tie-breaker, red "🚫 Don't switch right now" when all options are well above recent lows.
- **Entry flow on dashboards.** Selection card sits below the hero on every dashboard with state and utility pickers. State persists across fuel types; utility is saved per fuel. Picking a utility filters the page in place — Rate Reality Check, Available Plans, and Top 3 Rates re-scope to that utility; the calculator pre-selects it.
- **Welcome-back banner on the landing page** (`index.html`). Returning visitors get a one-click jump to their last-selected dashboard. "Start fresh" button clears the saved selection.
- **Open Graph + meta description tags** on every dashboard, so link previews on Slack, iMessage, and social platforms render with a real title and description.
- **Social-sharing button** in the savings calculator. "🔗 Share My Savings" generates a message with the user's calculated yearly savings and uses the Web Share API (with a clipboard fallback).
- **Market expansion plan** (`MARKET_EXPANSION.md`). Residential-only roadmap ranking deregulated states by similarity to the Ohio data model. Tier 1 drop-ins (PA, MD, IL, NY), Tier 2 single-fuel candidates (TX, CT, MA electric; MI, GA, DC gas), and explicit non-targets (NJ, NH, ME, VA/KY, FL).

### Changed
- **Rebranded from "Ohio Energy Tracker" to "RateSavvy."** Updated dashboard titles, OG/meta tags, topnav brand, share-button copy, PWA manifest name + short_name + description, README, and landing page. Domain set to ratesavvy.us (CNAME file added).
- **Reframed positioning from Ohio-specific to nationally focused.** Hero copy addresses anyone in a deregulated state. "Why does Ohio let me choose?" → "How energy choice works," with the full list of deregulated states so visitors from PA/NY/TX see themselves. Meta descriptions reference "deregulated US markets" rather than Ohio specifically. Utility names and data labels stay state-accurate.
- **"Top 5 Rates" → "Top 3 Rates"** with per-utility data buckets so the table actually populates when filtered to one utility (the previous version was hide-rows-after-render, which could empty the table).
- **"Market Leaderboard" → "Available Plans by Delivery Utility,"** with a one-line subtitle that explains what the section actually shows.
- **Market Dynamics charts collapsed by default.** They were rendering open and pushing actionable sections below the fold.
- **Workflow renamed** "Ohio Energy Tracker" → "RateSavvy Data Pipeline." Workflow now runs the test harness pre-flight and re-verifies the parquet schema post-scrape before letting the dashboard build proceed.

### Fixed
- **`build_dashboard.py` execution block.** The two `generate_energy_dashboard(...)` calls were indented inside the function body, so running the script defined the function and exited immediately without producing any HTML. Daily commits were only updating `allData.parquet`. Dedented to module scope.
- **Broken Ohio map removed.** The SVG map referenced `calc-util` but the calculator's select is `calc-utility`, so clicking map regions never updated the calculator. Removed the map entirely along with its CSS, JS, and wrapper div. Fixed the share button which had the same wrong ID.
- **Rate Reality Check recommendation contradictions.** When all three terms were at a similar premium and 24-month won as a tie-breaker, the per-term "don't lock 24mo" warning was being reused as the recommendation rationale, contradicting the recommendation itself. Recommendation text is now generated separately from per-term advice, with explicit "least-bad" framing when the recommendation is a tie-break rather than a high-confidence pick.

### Removed
- **Ohio map SVG** (see Fixed).
- **"Ohio Electric Market (Experimental)" hero badge** — duplicated info already implied by the state + utility selection card.
- **`PA_SCRAPER_BRIEF.md`** — working doc used to scope the PA scraper task. Now historical; the work it described is committed.
