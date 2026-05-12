import unittest
from datetime import datetime, timezone

from app.scheduler import is_within_business_hours, next_scheduled_at


class SchedulerTests(unittest.TestCase):
    def test_business_hours_chicago(self):
        now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
        self.assertTrue(is_within_business_hours(now, "09:00", "17:00", "America/Chicago"))

    def test_outside_business_hours_chicago(self):
        now = datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc)
        self.assertFalse(is_within_business_hours(now, "09:00", "17:00", "America/Chicago"))

    def test_next_schedule_uses_interval(self):
        now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(next_scheduled_at(now, 10), "2026-05-12T15:10:00+00:00")


if __name__ == "__main__":
    unittest.main()
