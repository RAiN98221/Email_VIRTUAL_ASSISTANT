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
            job_id = db.create_job('Test Campaign', [item], 10, 2, 25, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")
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
            job_id = db.create_job('Test Campaign', [item], 10, 3, 17, 5, True, "09:00", "17:00", "America/Chicago", False, "Text")

            job = db.list_jobs()[0]

            self.assertEqual(job["id"], job_id)
            self.assertEqual(job["campaign_name"], "Test Campaign")
            self.assertEqual(job["interval_jitter_minutes"], 3)
            self.assertEqual(job["daily_send_limit"], 17)
            self.assertEqual(job["max_failures"], 5)
            self.assertEqual(job["auto_pause_on_failure"], 1)

    def test_create_job_adds_unsubscribe_token(self):
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
            job_id = db.create_job('Test Campaign', [item], 10, 3, 17, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")
            queue_item = db.list_queue(job_id)[0]

            self.assertTrue(queue_item["unsubscribe_token"])

    def test_save_template_creates_and_updates_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            created = db.save_template("Outreach", "Hi {{first_name}}", "Hello")
            updated = db.save_template("Outreach V2", "Hello {{first_name}}", "Updated", created["id"])
            templates = db.list_templates()

            self.assertEqual(created["id"], updated["id"])
            self.assertEqual(updated["name"], "Outreach V2")
            self.assertEqual(updated["body"], "Updated")
            self.assertEqual(len(templates), 1)

    def test_email_status_summary_counts_queue_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            item = {
                "row_index": 2,
                "email": "one@example.com",
                "email_norm": "one@example.com",
                "first_name": "One",
                "last_name": "Example",
                "subject": "Hi",
                "body": "Hello",
                "row_data": {"email": "one@example.com"},
            }
            job_id = db.create_job('Test Campaign', [item], 10, 3, 17, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")
            db.mark_sent(db.list_queue(job_id)[0]["id"])

            summary = db.email_status_summary()
            counts = {item["key"]: item["count"] for item in summary["statuses"]}

            self.assertEqual(summary["total"], 1)
            self.assertEqual(counts["sent"], 1)
            self.assertEqual(counts["queued"], 0)
            self.assertEqual(counts["received"], 0)
            self.assertEqual(counts["replied"], 0)

    def test_record_inbound_reply_matches_sent_message_and_updates_counts(self):
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
            job_id = db.create_job("Reply Campaign", [item], 10, 3, 17, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")
            queue_item = db.list_queue(job_id)[0]
            db.mark_sent(queue_item["id"], smtp_message_id="<sent@example.com>")

            reply = db.record_inbound_reply(
                message_id="<reply@example.com>",
                from_email="person@example.com",
                from_email_norm="person@example.com",
                subject="Re: Hi",
                body="Interested.",
                received_at=db.utc_now(),
                references=["<sent@example.com>"],
            )
            updated_item = db.list_queue(job_id)[0]
            replies = db.list_replies()
            counts = {item["key"]: item["count"] for item in db.email_status_summary()["statuses"]}

            self.assertEqual(reply["matched_queue_item_id"], queue_item["id"])
            self.assertEqual(updated_item["status"], "replied")
            self.assertEqual(replies[0]["campaign_name"], "Reply Campaign")
            self.assertEqual(counts["received"], 1)
            self.assertEqual(counts["replied"], 1)

    def test_suppress_by_unsubscribe_token_records_suppression(self):
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
            job_id = db.create_job('Test Campaign', [item], 10, 3, 17, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")

            db.set_job_status(job_id, "paused", "Too many failures.")
            paused = db.list_jobs()[0]
            db.set_job_status(job_id, "running")
            running = db.list_jobs()[0]

            self.assertEqual(paused["pause_reason"], "Too many failures.")
            self.assertIsNone(running["pause_reason"])
            token = db.list_queue(job_id)[0]["unsubscribe_token"]

            unsubscribed = db.suppress_by_unsubscribe_token(token)
            suppressions = db.suppressed_emails()

            self.assertEqual(unsubscribed["email_norm"], "person@example.com")
            self.assertEqual(suppressions["person@example.com"]["reason"], "unsubscribed")
            self.assertEqual(suppressions["person@example.com"]["source"], "unsubscribe_link")

    def test_unsuppress_email_removes_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            db.suppress_email("Person@Example.com", "person@example.com", "manual", "manual", "test")

            removed = db.unsuppress_email("person@example.com")
            missing = db.unsuppress_email("person@example.com")

            self.assertTrue(removed)
            self.assertFalse(missing)
            self.assertEqual(db.suppressed_emails(), {})


if __name__ == "__main__":
    unittest.main()
