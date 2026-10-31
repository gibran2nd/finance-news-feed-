import unittest
from unittest import mock

from newsfeed import rates
from tests.helpers import NOW

CSV = ('Date,"1 Mo","2 Yr","3 Mo","5 Yr","10 Yr","30 Yr"\n'
       "10/30/2026,4.06,4.56,4.16,4.71,4.94,5.31\n"
       "10/29/2026,4.06,4.61,4.18,4.78,4.98,5.32\n")


class RatesTests(unittest.TestCase):
    def test_curve_levels_and_basis_point_changes(self):
        curve = rates.parse_curve(CSV)
        self.assertEqual(curve["date"], "Oct 30")
        ten = next(t for t in curve["tenors"] if t["label"] == "10Y")
        self.assertEqual((ten["level"], ten["change_bp"]), (4.94, -4))
        self.assertEqual((curve["spread_2s10s"], curve["spread_change"]), (38, 1))

    def test_malformed_curve_is_ignored(self):
        self.assertIsNone(rates.parse_curve("Date,10 Yr\n"))
        self.assertIsNone(rates.parse_curve(CSV.replace("4.94", "N/A")))

    def test_effr(self):
        text = '{"refRates":[{"percentRate":3.88,"targetRateFrom":3.75,"targetRateTo":4.0}]}'
        self.assertEqual(rates.parse_effr(text), {"effr": 3.88, "target_low": 3.75, "target_high": 4.0})
        self.assertIsNone(rates.parse_effr('{"refRates":[]}'))

    def test_panel_survives_without_fed_or_etfs(self):
        def fake(url):
            if "treasury" in url:
                return CSV
            raise OSError("down")
        with mock.patch.object(rates, "_get", side_effect=fake), \
             mock.patch.object(rates, "_from_yahoo", side_effect=OSError("down")):
            got = rates.fetch_rates(NOW)
        self.assertIsNone(got["fed"])
        self.assertEqual(got["bonds"], [])

    def test_no_curve_hides_panel(self):
        with mock.patch.object(rates, "_get", side_effect=OSError("down")):
            self.assertIsNone(rates.fetch_rates(NOW))


if __name__ == "__main__":
    unittest.main()
