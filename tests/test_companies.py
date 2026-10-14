import unittest

from newsfeed.companies import find_companies


class CompanyDetectionTests(unittest.TestCase):
    CASES = [
        ("Goldman Sachs profit jumps as dealmaking rebounds", ["Goldman Sachs"]),
        ("JPMorgan Chase's Dimon warns on rates", ["JPMorgan"]),
        ("Fed's Williams sees no need for rate hike", []),
        ("Dow ends higher as Nasdaq slips", []),
        ("Target Practice: Investors Aim at Small Caps", []),
        ("Target Corp cuts outlook", ["Target"]),
        ("Apple, Microsoft lead tech rally; Alphabet lags", ["Apple", "Microsoft", "Google"]),
        ("Lowe's Softens Full-Year Outlook", ["Lowe's"]),
        ("Bank of America fined $1.2 billion", ["Bank of America"]),
        ("Sherwin-Williams raises guidance", ["Sherwin-Williams"]),
        ("J&J's 6% slide on an imperfect quarter", ["Johnson & Johnson"]),
        ("Visa fees for H-1B workers rise", []),
        ("UNH beats Q3 expectations", ["UnitedHealth"]),
    ]

    def test_cases(self):
        for title, expected in self.CASES:
            self.assertEqual(find_companies(title), expected, title)


if __name__ == "__main__":
    unittest.main()
