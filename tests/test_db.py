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

    def test_delete_job_removes_job_and_queue_items(self):
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

            self.assertTrue(db.delete_job(job_id))
            self.assertEqual(db.list_jobs(), [])
            self.assertEqual(db.list_queue(job_id), [])
            self.assertFalse(db.delete_job(job_id))

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

    def test_delete_template_removes_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            created = db.save_template("Temp", "Subject", "Body")
            self.assertTrue(db.delete_template(created["id"]))
            self.assertEqual(db.list_templates(), [])
            self.assertFalse(db.delete_template(created["id"]))

    def test_delete_templates_by_name_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            db.save_template("Playwright Template 1", "S", "B")
            db.save_template("Playwright Template 2", "S", "B")
            db.save_template("Real Template", "S", "B")
            removed = db.delete_templates_by_name_prefix("Playwright Template")
            names = [row["name"] for row in db.list_templates()]

            self.assertEqual(removed, 2)
            self.assertEqual(names, ["Real Template"])

    def test_migration_adds_template_rotation_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            with db.connect() as conn:
                queue_columns = {row["name"] for row in conn.execute("PRAGMA table_info(queue_items)")}
                job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
            self.assertIn("template_name", queue_columns)
            self.assertIn("template_rotation", job_columns)

    def test_create_job_stores_template_name_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            items = [
                {
                    "row_index": 2,
                    "email": "a@example.com",
                    "email_norm": "a@example.com",
                    "subject": "Hi",
                    "body": "Hello",
                    "template_name": "Variant A",
                    "row_data": {},
                },
                {
                    "row_index": 3,
                    "email": "b@example.com",
                    "email_norm": "b@example.com",
                    "subject": "Hey",
                    "body": "Howdy",
                    "template_name": "Variant B",
                    "row_data": {},
                },
            ]
            job_id = db.create_job(
                "Rotation Campaign", items, 10, 2, 25, 3, True, "09:00", "17:00",
                "America/Chicago", False, "Text", template_rotation=["Variant A", "Variant B"],
            )
            queued = db.list_queue(job_id)
            job = db.list_jobs()[0]
            self.assertEqual([item["template_name"] for item in queued], ["Variant A", "Variant B"])
            self.assertEqual(job["template_rotation"], '["Variant A", "Variant B"]')

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
