"""Per-state scraper registry.

Each state lives in its own module and exposes:
  STATE  — two-letter state code (e.g. 'OH')
  scrape() -> pd.DataFrame — returns one combined dataframe of today's
                              electric + gas rows. Rows do NOT need a
                              `state` column; the dispatcher adds it.

To onboard a new state, add a module here and append it to ALL_SCRAPERS.
"""

from . import oh, pa, il

ALL_SCRAPERS = [oh, pa, il]
