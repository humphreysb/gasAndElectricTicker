# RateSavvy — Market Expansion Plan (Residential)

This document is the working roadmap for taking RateSavvy beyond Ohio. The focus is **residential customers only** — commercial/industrial markets have different rate structures, contract sizes, and regulatory rules that don't map to the current tool.

States are ranked by **how closely the official comparison site matches Ohio's data shape**, because that determines how much engineering work we'd need to onboard each one. The Ohio scraper at `energy_scraper.py` is the reference: it pulls a single HTML table per utility from `energychoice.ohio.gov`, parses fields (Term. Length, $/kWh or $/Mcf, Early Term. Fee, intro. price, promo. offers, Monthly Fee, Fixed Rate, Renew. Content, Supplier), and writes to `allData.parquet`.

## What "similar to Ohio" actually means

For a state to plug in cheaply, it needs:

1. **A state-run, centralized aggregator** — not a list of supplier links, but an actual comparison engine with current rates
2. **Tabular HTML/CSV output** that a Python scraper can hit without a headless browser
3. **Per-utility filtering** (Ohio scrapes by delivery utility; sites that only filter by ZIP are workable but messier)
4. **The same field set** — term length, fixed vs variable, monthly fee, ETF, intro pricing, renewable content
5. **Stable URL pattern** so the daily GitHub Action can hit it without drift

A state can be "deregulated" and still flunk all five (New Jersey, New Hampshire). Don't conflate market structure with data accessibility — the question is whether a scraper can run.

---

## 🏆 Tier 1 — Drop-in Candidates (mirror Ohio's model)

Highest similarity to Ohio. Both fuels, state-run sites, structured comparison tables. Scraper would be a ~20–40% adaptation of `energy_scraper.py`.

### 1. Pennsylvania — ✅ **SHIPPED**
- **Electric:** [PAPowerSwitch.com](https://www.papowerswitch.com)
- **Gas:** [PAGasSwitch.com](https://www.pagasswitch.com)
- **Run by:** PA Public Utility Commission
- **Status:** Live in `scrapers/pa.py`. Daily run emits `pa-electric_dashboard.html` and `pa-gas_dashboard.html`.
- **Utilities covered:** Electric (8): PECO, PPL, Duquesne, Met-Ed, Penelec, Penn Power, West Penn Power, UGI. Gas (6): UGI, Columbia Gas of PA, PECO Gas, Peoples, National Fuel, PGW.
- **Notes:** Integer IDs used as `Provider` keys (e.g. 1182 for PECO). Gas rates normalized from $/Ccf to $/Mcf to match Ohio's unit. Adding PA validated the multi-state architecture end-to-end — onboarding the next state should follow the same shape: one scraper module plus four small registry entries.

### ~~2. Maryland~~ — ❌ **Dormant (regulatory exit, January 2025)**
- **Sites:** [mdelectricchoice.com](https://www.mdelectricchoice.com) (run by MD PSC, replaced `marylandelectricchoice.com`) and [mdgaschoice.com](https://www.mdgaschoice.com).
- **Status:** Comparison engines are up but **the marketplace is empty**. Every utility (BGE, Pepco, Delmarva, Potomac Edison, Choptank, SMECO on electric; BGE Gas, Washington Gas on gas) returns "Sorry, no current offers matched your search" as of May 2026.
- **Why:** Per the MD PSC site: *"Senate Bill 1 of the 2024 Maryland General Assembly session enacted major reforms in the retail energy supply marketplace … As a result of these changes, some retail suppliers have made the business decision to no longer offer supply to residential customers."* Effective Jan 1, 2025.
- **Decision:** Skip Maryland until the marketplace reactivates. Building a daily scraper now would burn requests for zero rows. Re-check quarterly via the [Why Fewer Offers?](https://www.mdelectricchoice.com/why-you-may-see-fewer-offers/) page.

### 3. Illinois
- **Electric:** [PlugInIllinois.org](https://www.pluginillinois.org)
- **Gas:** [Illinois Commerce Commission gas comparison](https://www.icc.illinois.gov)
- **Run by:** Illinois Commerce Commission
- **Why:** Two big utilities each: **ComEd, Ameren** for electric; **Peoples Gas, Nicor Gas, North Shore Gas, Ameren Illinois** for gas. Electric site is straightforward; gas data is on the ICC site and historically less polished.
- **Estimated scraper effort:** Medium. Electric mirrors Ohio. Gas may need its own parser if the ICC publishes PDFs/CSV instead of HTML tables.

### 4. New York
- **Electric:** [PowerToChoose.ny.gov](http://www.powertochoose.ny.gov)
- **Gas:** Same portal
- **Run by:** NY Department of Public Service
- **Why:** Both fuels in one portal. Utilities are familiar names: **Con Edison, National Grid, NYSEG, RG&E, Orange & Rockland, Central Hudson**. Gas: **Con Edison, National Grid (downstate + upstate), NYSEG, Central Hudson**.
- **Estimated scraper effort:** Medium. The site's structure differs more from Ohio's than PA does — expect a separate parser. Worth it because of market size.

---

## 🎯 Tier 2 — Single-Fuel Drop-ins

Same model as Tier 1 but only one fuel. Each is straightforward to add once we have the multi-state architecture in place.

### Electric only
| State | Site | Notes |
|---|---|---|
| **Texas** | [PowerToChoose.org](https://www.powertochoose.org) | Biggest deregulated electric market in the US (~25M people in service territory). **Caveat:** Texas uses a "REP" model — there is no traditional regulated wires-utility-plus-competitive-supplier split like in Ohio. Plans come bundled. We'd need to relabel "utility/supplier" terminology for TX cards. |
| **Connecticut** | [EnergizeCT.com](https://energizect.com) | Two utilities (Eversource, UI). Clean comparison site. |
| **Massachusetts** | [EnergySwitchMA.gov](https://energyswitchma.gov) | Three utilities (Eversource, National Grid, Unitil). Good comparison portal. |

### Gas only
| State | Site | Notes |
|---|---|---|
| **Michigan** | [Compare MI Gas](https://www.lara.state.mi.us/mpsc/gas/compare/) | Older-looking state site but tabular data. Major utilities: Consumers Energy, DTE, SEMCO. |
| **Georgia** | [GA PSC Marketers' Pricing](https://psc.ga.gov/utilities/natural-gas/marketers-pricing-comparison/) | Unique market — gas is fully deregulated statewide (no default utility supply); residential **must** pick a marketer. Atlanta Gas Light handles delivery. |
| **Washington, D.C.** | [DC Power Connect](https://www.dcpowerconnect.com) | Single-utility market (Washington Gas). Very small but the site is structured. |

---

## 🚧 Architecture work that lands before any new state

Onboarding one state is a scraper change. Onboarding the second state requires architectural work first — otherwise the codebase will balloon. Bullet list:

1. **Multi-state data model.** `allData.parquet` currently has no `state` column. Add one (default `OH`) and migrate. The scraper and dashboard build need to filter by state.
2. **Per-state `providers.py`.** Today there's one `elec`/`gas` dict. Move to `providers/{OH,PA,MD,…}.py` or a single dict-of-dicts keyed by state.
3. **Per-state scraper modules.** `energy_scraper.py` becomes a dispatcher; per-state logic lives in `scrapers/oh.py`, `scrapers/pa.py`, etc. The GitHub Action loops over states or runs them in parallel jobs.
4. **State selector wired to filtering.** The dashboard already has a state picker UI — currently OH-only, but the structure is there. Wire the selector to the data filter once a second state's data is available.
5. **EIA macro overlay per state.** Today the dashboard overlays Ohio's EIA residential average. Need state-keyed EIA series IDs (e.g., `ELEC.PRICE.OH-RES.M` → swap state code).
6. **Weather overlay coordinates per state.** Currently hardcoded to Columbus (39.96, -82.99). Make it a per-state config — pick a representative metro per state.
7. **BBB cache scoping.** `bbb_ratings.json` is keyed by supplier name. Suppliers can operate in multiple states, but the name might vary slightly — review for collisions before adding states.
8. **Output file naming.** `electric_dashboard.html` and `gas_dashboard.html` become per-state: `oh-electric.html`, `pa-electric.html`, etc. The state picker on the homepage routes to the right file. Or one dashboard per fuel with JS filtering — TBD.

**My recommendation:** do steps 1–4 before adding PA, even though it's tempting to just fork the scraper. Otherwise we're rewriting the dashboard twice.

---

## ❌ Not pursuing (residential context)

States where residential deregulation exists but data is too scattered to scrape reliably:

- **New Jersey** — supplier list only, no live comparison engine
- **New Hampshire** — supplier list only
- **Maine** — standard offer rates published, but no apples-to-apples comparison
- **Virginia / Kentucky** — gas choice exists but only in narrow utility service areas, no statewide aggregator
- **Florida** — gas choice is commercial-only at the residential level there's no meaningful market

These can be revisited if/when their PUCs publish structured data, but they're not worth scraper-engineering effort today.

---

## Suggested order

1. ~~**Architecture work (items 1–4 above)**~~ ✅ Done. Foundation is in.
2. ~~**Pennsylvania (both fuels)**~~ ✅ Done. Multi-state model validated end-to-end.
3. ~~**Maryland**~~ ❌ Skipped — dormant marketplace, see above. Re-check quarterly.
4. **Illinois (electric, gas separately if scrapable)** — 🟡 brief: [`IL_SCRAPER_BRIEF.md`](IL_SCRAPER_BRIEF.md). Electric side confirmed scrapable: `icc.illinois.gov/plugin/offers?said=N` returns a server-rendered HTML table parseable by `pandas.read_html`. Gas may be PDF-only on the ICC site; if so, ship electric-only and revisit.
5. **New York (both fuels)** — 🟡 brief: [`NY_SCRAPER_BRIEF.md`](NY_SCRAPER_BRIEF.md). Single comparison site for both fuels, six EDCs — the largest utility count of any Phase 1 state. Investigation pending.
6. **Texas (electric)** — Phase 2. Biggest single-state audience, validates the REP-only market model (no traditional utility-supplier split).
7. **Everything else** — once Phase 1 lands, each additional state is a contained scraper + utility-map PR.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the multi-provider hosting plan (GitHub Actions + Cloudflare Pages + R2) and the free-tier discipline rules.

---
*Last updated: 2026-05-19*
