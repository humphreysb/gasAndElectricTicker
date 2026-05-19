# RateSavvy Architecture

This is the running engineering doc. It captures (a) the current shape of the system, (b) the planned move to Cloudflare, and (c) the discipline rules that keep us on free tiers across providers.

## 1. Today's shape

```
┌──────────────────────────────────────────────────────────────────┐
│   GitHub Actions (free: 2000 min/mo)                             │
│   ┌────────────────────────────────────────────────────────────┐ │
│   │  Daily 13:00 UTC                                           │ │
│   │  1. Run tests (tests/)                                     │ │
│   │  2. Run scrapers (energy_scraper.py → dispatcher)          │ │
│   │       - scrapers/oh.py   → Energy Choice Ohio              │ │
│   │       - scrapers/pa.py   → PAPowerSwitch + PAGasSwitch     │ │
│   │       - scrapers/md.py   → MarylandElectricChoice + …      │ │  (planned)
│   │       - scrapers/il.py   → PlugInIllinois + ICC            │ │  (planned)
│   │       - scrapers/ny.py   → PowerToChoose.ny.gov            │ │  (planned)
│   │  3. Validate schema (tests/test_data_schema.py)            │ │
│   │  4. Build per-state dashboards (build_dashboard.py)        │ │
│   │  5. Commit + push                                          │ │
│   └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │   git push
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│   GitHub Pages (currently serving ratesavvy.us via CNAME)         │
│   Static HTML + CSS + JS, no server-side anything.                │
└──────────────────────────────────────────────────────────────────┘
```

**Data:** one parquet file (`allData.parquet`) committed to the repo. ~1.6 MB at OH + PA. Scales to maybe 50–100 MB before git starts to complain.

**Per-state dashboards:** `{state-prefix}-electric_dashboard.html` and `{state-prefix}-gas_dashboard.html`. Ohio keeps the legacy filenames (`electric_dashboard.html`, `gas_dashboard.html`) for backward compatibility with the existing GitHub Pages URLs.

## 2. Where we're going (Cloudflare-aware)

The plan is to migrate hosting + heavy data storage to Cloudflare while keeping the dev experience git-centric. **No Cloudflare Workers in production unless they earn their keep** — GitHub Actions is generous enough for our compute needs and adding Workers is a free-tier risk + ops surface we don't need.

```
                                                          ┌────────────────────────────┐
                                                          │  Cloudflare Pages          │
              git push (main)                             │  (replaces GitHub Pages)   │
   ┌───────────────────────────────┐                      │  - ratesavvy.us            │
   │  GitHub Actions               │  ──────────────────▶ │  - Free: 500 builds/mo,    │
   │  Daily scrape + build         │   triggers Pages     │    unlimited bandwidth     │
   └───────────────────────────────┘   rebuild via git    └────────────────────────────┘
                  │
                  │  parquet writes (when too big for git)
                  ▼
   ┌───────────────────────────────┐
   │  Cloudflare R2                │
   │  - Free: 10 GB storage         │  HTTP GET from build job to fetch latest snapshot
   │  - Zero egress fees           │  ◀────────────────────────────────────────────────
   │  - S3-compatible API          │
   └───────────────────────────────┘
```

### Why not Cloudflare Workers?
- Free tier is 100k requests/day, which sounds like a lot but a popular page with charts can blow it on view spikes.
- Workers force JS/TypeScript, which fragments the codebase (current pipeline is all Python).
- Static-first wins for SEO, caching, and PWA install — and we're already there.
- **Only add a Worker when there's a feature that genuinely needs server-side compute** — e.g., live API for third-party tools, or a personalized recommendation endpoint that's too dynamic for static HTML.

### Why not Cloudflare D1?
- We have ≤200k rows total. Pandas + parquet is faster, free, and doesn't require a query language.
- D1 makes sense if we add interactive filters that aren't pre-baked. Probably not for a while.

### What Cloudflare DOES give us soon
- **Pages**: faster CDN, better analytics, and the platform's deploy hooks are nicer than GH Pages.
- **R2**: when `allData.parquet` outgrows git, R2 is the right home. The build job downloads it at the start of each run, appends, re-uploads, and writes the parquet's hash to a small `data.json` in the repo so the dashboard build knows which version it's looking at.
- **Cache rules**: aggressive caching on static assets, with a short TTL on the dashboard HTML so daily updates show up quickly.

## 3. Private files

Some things shouldn't be in the public repo:
- Scrape session secrets, if any state's marketplace requires auth or cookie tokens.
- Raw HTML snapshots of pages we're parsing (could contain personally identifying data depending on the site).
- API keys (EIA, BBB, anything paid).
- Larger backfill artifacts that bloat the public repo unnecessarily.

**Strategy:** a separate `humphreysb/ratesavvy-private` repo for secrets and a Cloudflare R2 bucket for bulky private data.

- **Secrets** live in `ratesavvy-private`, pulled into GitHub Actions via a fine-grained deploy token. Public CI references them via repository secrets only — never checked in.
- **Bulky private data** (raw HTML snapshots, partial backfills, scraping logs) goes to R2 in a private bucket. The scraper writes to R2 directly with credentials sourced from GH Actions secrets.

For Phase 1 we don't strictly need either yet — keep deferring until a real secret or large file forces the move.

## 4. Free-tier discipline

Hard rules to keep this on free tiers across the board:

| Resource | Free limit | Our budget |
|---|---|---|
| GitHub Actions minutes | 2000/month | ≤300/month (15 min/day × 30 days = 450, but daily run is currently ~3 min) |
| GitHub repo size | soft limit ~5 GB, hard ~10 GB | ≤500 MB. Parquet must move to R2 long before this. |
| Cloudflare Pages builds | 500/month | ≤60/month (one build per push to `main`, daily run = ~30/mo) |
| Cloudflare R2 storage | 10 GB | ≤2 GB normalized parquet, ≤5 GB raw snapshots |
| Cloudflare R2 Class A ops (writes) | 1M/month | ~30/day = 900/month, well under |
| Cloudflare R2 Class B ops (reads) | 10M/month | ~30/day fetches by build job = trivial |
| Cloudflare Workers | 100k req/day | **target: zero Workers** |
| Cloudflare D1 | 5M reads/day, 5 GB | **target: do not use** |
| Cloudflare KV | 100k reads/day, 1 GB | **target: do not use unless trivially small** |

### What this means for design
- **Don't add a Worker** unless a concrete feature literally cannot be served from a static HTML build. Recompute on each daily build → serve static.
- **Don't denormalize early.** Per-state HTML files are cheap; per-state-per-utility HTML files would explode the build artifact count. The current state+utility-in-URL approach is right.
- **Don't introduce new dependencies** without thinking about CI install time. `pip install -r requirements.txt` is currently ~30 s; keep it under a minute.
- **Don't fetch from third-party APIs (BBB, EIA, weather) on every page view.** They're already pre-baked into the HTML at build time, which is correct. Keep it that way.

## 5. Phase 1 expansion plan

States to onboard, in order:

| State | Both fuels? | Site | Status |
|---|---|---|---|
| OH | Yes | Energy Choice Ohio | ✅ live |
| PA | Yes | PAPowerSwitch + PAGasSwitch | ✅ live |
| MD | Yes | MarylandElectricChoice + MDGasChoice | 🟡 next — see `MD_SCRAPER_BRIEF.md` |
| IL | Yes | PlugInIllinois + ICC | 🟡 next — see `IL_SCRAPER_BRIEF.md` |
| NY | Yes | PowerToChoose.ny.gov | 🟡 next — see `NY_SCRAPER_BRIEF.md` |

Each scraper follows the pattern PA established: a single module in `scrapers/<code>.py` exposing `STATE` and `scrape()`, an entry in `providers.STATES`, registration in `scrapers/__init__.py`, and a `STATE_CONFIG` entry in `build_dashboard.py`. The interface tests (`tests/test_scraper_interface.py`) enforce the contract automatically.

## 6. Migration order (when Cloudflare actually happens)

1. **Cloudflare Pages**: point ratesavvy.us at a CF Pages project that pulls from this same git repo. Side-by-side with GH Pages first (use a `staging.ratesavvy.us` subdomain on CF). Cut over once verified.
2. **R2 for parquet**: when `allData.parquet` crosses ~50 MB (probably after IL + NY + a few weeks of daily data), move it to R2. Build job downloads at start, uploads at end. The `data.json` metadata file in git stays small and is the canonical pointer.
3. **Private repo + R2 private bucket**: only when we have a concrete need (raw snapshot retention, paid API keys).
4. **CF Workers**: only when a feature legitimately requires it. Likely candidates would be a "live email alerts" endpoint or "embed our widget on your site" feature — neither is on the near-term roadmap.

---
*Last updated: 2026-05-19*
