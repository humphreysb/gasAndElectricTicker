"""Interface contract tests for per-state scrapers.

These tests don't hit the network — they just verify each scraper module
satisfies the contract the dispatcher (`energy_scraper.py`) and the
dashboard builder (`build_dashboard.py`) rely on. They catch the kind of
bug where a new state's scraper exposes the wrong attribute name, forgets
to register its utilities, or drifts from the column shape that every
other scraper writes into `allData.parquet`.

Run from repo root:
    python -m unittest tests.test_scraper_interface
"""
import unittest

import providers
from scrapers import ALL_SCRAPERS


class ScraperInterfaceTests(unittest.TestCase):
    """Every registered scraper must look the same to the dispatcher."""

    def test_at_least_one_scraper_registered(self):
        self.assertGreater(len(ALL_SCRAPERS), 0, "scrapers/__init__.py registers nothing")

    def test_each_scraper_exposes_state_code(self):
        for s in ALL_SCRAPERS:
            with self.subTest(scraper=s.__name__):
                self.assertTrue(hasattr(s, 'STATE'), f"{s.__name__} missing STATE")
                self.assertIsInstance(s.STATE, str)
                self.assertEqual(len(s.STATE), 2, f"{s.__name__}.STATE must be 2 letters")
                self.assertEqual(s.STATE, s.STATE.upper(), f"{s.__name__}.STATE must be uppercase")

    def test_each_scraper_exposes_scrape_callable(self):
        for s in ALL_SCRAPERS:
            with self.subTest(scraper=s.__name__):
                self.assertTrue(hasattr(s, 'scrape'), f"{s.__name__} missing scrape()")
                self.assertTrue(callable(s.scrape), f"{s.__name__}.scrape is not callable")

    def test_state_codes_are_unique(self):
        codes = [s.STATE for s in ALL_SCRAPERS]
        self.assertEqual(len(codes), len(set(codes)),
                         f"duplicate STATE codes in scrapers: {codes}")


class ProvidersRegistryTests(unittest.TestCase):
    """Every state with a scraper must have a matching providers entry."""

    def test_every_scraper_has_a_providers_entry(self):
        for s in ALL_SCRAPERS:
            with self.subTest(state=s.STATE):
                self.assertIn(s.STATE, providers.STATES,
                              f"providers.STATES missing entry for {s.STATE}")

    def test_each_providers_entry_has_elec_and_gas(self):
        for state, entry in providers.STATES.items():
            with self.subTest(state=state):
                self.assertIn('elec', entry, f"providers.STATES[{state!r}] missing 'elec'")
                self.assertIn('gas', entry, f"providers.STATES[{state!r}] missing 'gas'")
                self.assertIsInstance(entry['elec'], dict)
                self.assertIsInstance(entry['gas'], dict)
                # At least one utility per fuel — empty dicts are almost always a bug.
                self.assertGreater(len(entry['elec']) + len(entry['gas']), 0,
                                   f"providers.STATES[{state!r}] has no utilities at all")

    def test_for_state_lookup_works(self):
        for s in ALL_SCRAPERS:
            with self.subTest(state=s.STATE):
                entry = providers.for_state(s.STATE)
                self.assertEqual(entry, providers.STATES[s.STATE])

    def test_backward_compat_elec_gas_aliases(self):
        # Legacy callers reference providers.elec / providers.gas; those
        # must still resolve to Ohio's mapping until everyone migrates.
        self.assertEqual(providers.elec, providers.STATES['OH']['elec'])
        self.assertEqual(providers.gas, providers.STATES['OH']['gas'])


if __name__ == '__main__':
    unittest.main()
