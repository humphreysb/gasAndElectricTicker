"""Schema tests for `allData.parquet`.

The dashboard builder assumes a fixed column shape. Any scraper that
writes rows with a different shape will silently corrupt the union.
These tests assert the parquet file at the repo root carries every
column the builder needs, with the expected dtypes.

Run from repo root:
    python -m unittest tests.test_data_schema
"""
import os
import unittest

import pandas as pd


PARQUET = 'allData.parquet'

# The union of columns every scraper must produce. If you add a column
# here, you also need to add it to every scraper's output.
REQUIRED_COLUMNS = {
    'Supplier', 'Rate Type', 'Renew. Content', 'intro. price',
    'Term. Length', 'Early Term. Fee', 'Monthly Fee', 'promo. offers',
    'electric', 'rate', 'Fixed Rate', 'Todays Data', 'Date', 'Provider',
    'state',
}


@unittest.skipUnless(os.path.exists(PARQUET), f"{PARQUET} not present; skipping schema tests")
class DataSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_parquet(PARQUET)

    def test_all_required_columns_present(self):
        missing = REQUIRED_COLUMNS - set(self.df.columns)
        self.assertFalse(missing, f"allData.parquet missing columns: {missing}")

    def test_state_column_never_null(self):
        nulls = self.df['state'].isna().sum()
        self.assertEqual(nulls, 0, f"{nulls} rows have null state — backfill broke")

    def test_electric_is_boolean(self):
        # pandas may store as object or bool; both are acceptable
        # as long as every non-null value is True or False.
        vals = set(self.df['electric'].dropna().unique())
        self.assertTrue(vals.issubset({True, False}),
                        f"electric column has non-boolean values: {vals}")

    def test_rate_is_numeric(self):
        self.assertTrue(pd.api.types.is_numeric_dtype(self.df['rate']),
                        f"rate column is not numeric (dtype={self.df['rate'].dtype})")

    def test_date_is_datetime(self):
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(self.df['Date']),
                        f"Date column is not datetime (dtype={self.df['Date'].dtype})")

    def test_no_duplicate_todays_data_flag_per_state(self):
        # Sanity: 'Todays Data' should be True only for the most recent
        # scrape's rows. Multiple scrape dates with Todays Data=True means
        # the scraper didn't reset the flag on prior runs.
        todays = self.df[self.df['Todays Data'] == True]
        if todays.empty:
            self.skipTest("no rows flagged as Todays Data")
        # Per state, all rows tagged Todays Data should share the same date.
        for state, group in todays.groupby('state'):
            with self.subTest(state=state):
                unique_dates = group['Date'].dt.normalize().unique()
                self.assertEqual(
                    len(unique_dates), 1,
                    f"state {state}: 'Todays Data' flag spans {len(unique_dates)} "
                    f"dates — prior runs weren't reset"
                )


if __name__ == '__main__':
    unittest.main()
