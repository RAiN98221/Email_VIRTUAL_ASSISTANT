import tempfile
import unittest
from pathlib import Path
from app import db


class DbTests(unittest.TestCase):
    def test_mark_sent_records_contacted_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            item = {
                "row_index": 2,
                "email": "Person@Example.com",
                "email_norm": "person@example.com",
                "first_name": "Person",
                "last_name": "Example",
                "subject": "Hi",
                "body": "Hello",
                "row_data": {"email": "Person@Example.com"},
            }
            job_id = db.create_job([item], 10, 2, 25, "09:00", "17:00", "America/Chicago", False, "Text")
            queue_item = db.list_queue(job_id)[0]
            db.mark_sent(
                queue_item["id"],
                smtp_message_id="request-id",
                verification_status="sent_mail_found",
                verification_detail="found in Sent Mail",
            )
            updated_item = db.list_queue(job_id)[0]
            history = db.contacted_history()
            self.assertEqual(updated_item["smtp_message_id"], "request-id")
            self.assertEqual(updated_item["verification_status"], "sent_mail_found")
            self.assertIsNone(updated_item["error"])
            self.assertEqual(history[0]["email_norm"], "person@example.com")
            self.assertEqual(history[0]["job_id"], job_id)

    def test_create_job_stores_daily_cap_and_jitter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            item = {
                "row_index": 2,
                "email": "Person@Example.com",
                "email_norm": "person@example.com",
                "first_name": "Person",
                "last_name": "Example",
                "subject": "Hi",
                "body": "Hello",
                "row_data": {"email": "Person@Example.com"},
            }
            job_id = db.create_job([item], 10, 3, 17, "09:00", "17:00", "America/Chicago", False, "Text")

            job = db.list_jobs()[0]

            self.assertEqual(job["id"], job_id)
            self.assertEqual(job["interval_jitter_minutes"], 3)
            self.assertEqual(job["daily_send_limit"], 17)


if __name__ == "__main__":
    unittest.main()
