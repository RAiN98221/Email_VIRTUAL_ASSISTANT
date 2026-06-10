import tempfile
import smtplib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from app import db
from app.graph import SendResult, SendVerification
from app.scheduler import (
    is_within_business_hours,
    local_day_window_utc,
    next_scheduled_at,
    process_due_items,
    smtp_failure_suppression_reason,
)


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

    def test_next_schedule_applies_bounded_jitter(self):
        now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
        with patch("app.scheduler.random.randint", return_value=-2) as randint:
            scheduled = next_scheduled_at(now, 10, 2)

        randint.assert_called_once_with(-2, 2)
        self.assertEqual(scheduled, "2026-05-12T15:08:00+00:00")

    def test_next_schedule_never_delays_less_than_one_minute(self):
        now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
        with patch("app.scheduler.random.randint", return_value=-10):
            scheduled = next_scheduled_at(now, 5, 10)

        self.assertEqual(scheduled, (now + timedelta(minutes=1)).isoformat())

    def test_local_day_window_uses_job_timezone(self):
        now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
        start, end = local_day_window_utc(now, "America/Chicago")

        self.assertEqual(start.isoformat(), "2026-05-12T05:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-05-13T05:00:00+00:00")

    def test_process_due_items_honors_daily_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            items = [
                {
                    "row_index": 2,
                    "email": "one@example.com",
                    "email_norm": "one@example.com",
                    "first_name": "One",
                    "last_name": "Example",
                    "subject": "Hi",
                    "body": "Hello",
                    "row_data": {"email": "one@example.com"},
                },
                {
                    "row_index": 3,
                    "email": "two@example.com",
                    "email_norm": "two@example.com",
                    "first_name": "Two",
                    "last_name": "Example",
                    "subject": "Hi",
                    "body": "Hello",
                    "row_data": {"email": "two@example.com"},
                },
            ]
            job_id = db.create_job('Test Campaign', items, 10, 0, 1, 3, True, "00:00", "23:59", "UTC", False, "Text")
            first_item = db.list_queue(job_id)[0]
            db.mark_sent(
                first_item["id"],
                smtp_message_id="<one@example.com>",
                verification_status="skipped",
                verification_detail="test",
            )
            graph = MagicMock()
            graph.send_mail.return_value = SendResult(
                smtp_accepted=True,
                message_id="<two@example.com>",
                verification=SendVerification("skipped", "test"),
            )

            process_due_items(graph)

            graph.send_mail.assert_not_called()
            self.assertEqual(db.list_queue(job_id)[1]["status"], "pending")

    def test_hard_smtp_failure_classifies_as_bounced(self):
        exc = smtplib.SMTPRecipientsRefused(
            {"bad@example.com": (550, b"5.1.1 User unknown")}
        )

        self.assertEqual(smtp_failure_suppression_reason(exc), "bounced")

    def test_process_due_items_suppresses_hard_smtp_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            items = [
                {
                    "row_index": 2,
                    "email": "bad@example.com",
                    "email_norm": "bad@example.com",
                    "first_name": "Bad",
                    "last_name": "Example",
                    "subject": "Hi",
                    "body": "Hello",
                    "row_data": {"email": "bad@example.com"},
                },
            ]
            job_id = db.create_job('Test Campaign', items, 10, 0, 25, 3, True, "00:00", "23:59", "UTC", False, "Text")
            graph = MagicMock()
            graph.send_mail.side_effect = smtplib.SMTPRecipientsRefused(
                {"bad@example.com": (550, b"5.1.1 User unknown")}
            )

            process_due_items(graph)

            queue_item = db.list_queue(job_id)[0]
            suppressions = db.suppressed_emails()
            self.assertEqual(queue_item["status"], "failed")
            self.assertEqual(suppressions["bad@example.com"]["reason"], "bounced")
            self.assertEqual(suppressions["bad@example.com"]["source"], "smtp_failure")

    def test_process_due_items_auto_pauses_after_failure_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            items = [
                {
                    "row_index": 2,
                    "email": "bad@example.com",
                    "email_norm": "bad@example.com",
                    "first_name": "Bad",
                    "last_name": "Example",
                    "subject": "Hi",
                    "body": "Hello",
                    "row_data": {"email": "bad@example.com"},
                },
            ]
            job_id = db.create_job('Test Campaign', items, 10, 0, 25, 1, True, "00:00", "23:59", "UTC", False, "Text")
            graph = MagicMock()
            graph.send_mail.side_effect = RuntimeError("SMTP credentials rejected")

            process_due_items(graph)

            job = db.list_jobs()[0]
            self.assertEqual(job["status"], "paused")
            self.assertEqual(job["pause_reason"], "Auto-paused after 1 failed send attempt(s).")

    def test_process_due_items_respects_auto_pause_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            items = [
                {
                    "row_index": 2,
                    "email": "bad@example.com",
                    "email_norm": "bad@example.com",
                    "first_name": "Bad",
                    "last_name": "Example",
                    "subject": "Hi",
                    "body": "Hello",
                    "row_data": {"email": "bad@example.com"},
                },
            ]
            db.create_job('Test Campaign', items, 10, 0, 25, 1, False, "00:00", "23:59", "UTC", False, "Text")
            graph = MagicMock()
            graph.send_mail.side_effect = RuntimeError("SMTP credentials rejected")

            process_due_items(graph)

            job = db.list_jobs()[0]
            self.assertEqual(job["status"], "running")
            self.assertIsNone(job["pause_reason"])


if __name__ == "__main__":
    unittest.main()
