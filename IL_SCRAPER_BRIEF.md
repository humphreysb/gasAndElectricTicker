# Task brief: Add an Illinois scraper to RateSavvy

Run only after MD ships and you've confirmed the pattern still holds. Same shape as `MD_SCRAPER_BRIEF.md`; this brief focuses on the Illinois-specific bits.

## Sites

- **Electric:** https://www.pluginillinois.org — run by the Illinois Commerce Commission (ICC).
- **Gas:** https://www.icc.illinois.gov (Natural Gas → Choose Your Supplier section). **Heads up:** the ICC's gas data is historically less polished than the electric site — possibly PDF, possibly a list rather than a comparison engine. If it's not scrapable without a headless browser, ship electric-only for IL and leave gas as a `# TODO` with a note in `MARKET_EXPANSION.md`.

## Residential utilities

**Electric (EDCs):**
- ComEd (Commonwealth Edison — Chicago metro)
- Ameren Illinois (downstate)

**Gas (LDCs):**
- Peoples Gas (Chicago)
- North Shore Gas (Chicago north suburbs)
- Nicor Gas (most of northern IL outside Chicago city)
- Ameren Illinois (downstate)

## What's different from PA/MD

- **Two-EDC simplicity.** Only ComEd and Ameren on the electric side. The scraper is shorter.
- **Gas may be PDF-only.** If `pluginillinois.org` doesn't cover gas and the ICC site only publishes a PDF rate sheet, scrape the PDF with `tabula-py`… **no — don't add a new dependency.** Instead, scrape the PDF text via `pdftotext` (system tool — verify it's available in `ubuntu-latest` GitHub runners) or skip gas entirely. **Default: skip gas for IL in this pass.**
- **Threshold rates** in `STATE_CONFIG`: ComEd's PTC has been ~9–11¢/kWh recently; Ameren's similar. Use 0.10 as a starting point.

## Deliverable

- `scrapers/il.py` (electric only is acceptable for v1).
- `providers.STATES['IL']` populated.
- `scrapers/__init__.py` updated.
- `STATE_CONFIG['IL']` in `build_dashboard.py`.
- `il-electric_dashboard.html` builds. If gas is skipped, do not register `il-gas_dashboard.html` and skip the gas threshold field.

## Out of scope

Everything from `MD_SCRAPER_BRIEF.md`'s "Out of scope" section also applies here.
