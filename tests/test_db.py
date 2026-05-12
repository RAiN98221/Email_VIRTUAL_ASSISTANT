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
            job_id = db.create_job([item], 10, "09:00", "17:00", "America/Chicago", False, "Text")
            queue_item = db.list_queue(job_id)[0]
            db.mark_sent(queue_item["id"], "request-id")
            history = db.contacted_history()
            self.assertEqual(history[0]["email_norm"], "person@example.com")
            self.assertEqual(history[0]["job_id"], job_id)


if __name__ == "__main__":
    unittest.main()
