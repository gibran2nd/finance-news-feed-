import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from newsfeed import health
from tests.helpers import NOW


def stat(newest_days, error=None, fresh=5):
    return {"section": "Deals", "label": "Feed", "url": "u", "error": error, "fresh": fresh,
            "kept": fresh, "junk": 0, "off_topic": 0,
            "newest": NOW - timedelta(days=newest_days) if newest_days is not None else None}


class HealthTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.alert = tmp / "alerts.md"
        for name, val in (("HEALTH_FILE", tmp / "h.json"), ("FEED_ALERT_FILE", self.alert)):
            p = mock.patch.object(health, name, val)
            p.start()
            self.addCleanup(p.stop)

    def run_n(self, st, n):
        for _ in range(n):
            result = health.update_feed_health([st], NOW)
        return result

    def test_fresh_feed_is_ok(self):
        h, alerts = self.run_n(stat(1), 3)
        self.assertEqual(h["Deals | Feed"]["status"], "ok")
        self.assertEqual(alerts, [])
        self.assertFalse(self.alert.exists())

    def test_stale_feed_with_recent_week_items_is_flagged(self):
        h, alerts = self.run_n(stat(6), 3)      # still inside the 7-day window
        self.assertEqual(h["Deals | Feed"]["status"], "stale")
        self.assertEqual(len(alerts), 1)
        self.assertIn("Feed", self.alert.read_text())

    def test_recovery_removes_alert_file(self):
        self.run_n(stat(6), 3)
        self.run_n(stat(1), 1)
        self.assertFalse(self.alert.exists())


if __name__ == "__main__":
    unittest.main()
