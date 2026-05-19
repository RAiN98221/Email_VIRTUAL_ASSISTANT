import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.main import QueueRequest, create_job


class MainTests(unittest.TestCase):
    def test_create_job_honors_send_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = QueueRequest(
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                send_limit=2,
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = [
                    {
                        "name": "test_contacts.csv",
                        "path": str(Path("test_contacts.csv").resolve()),
                        "default": False,
                    }
                ]
                result = create_job(payload)
            self.assertEqual(result["queued"], 2)
            self.assertEqual(len(db.list_queue(result["job_id"])), 2)

    def test_create_job_honors_selected_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = QueueRequest(
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                selected_row_indexes=[3, 5],
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = [
                    {
                        "name": "test_contacts.csv",
                        "path": str(Path("test_contacts.csv").resolve()),
                        "default": False,
                    }
                ]
                result = create_job(payload)
            queued = db.list_queue(result["job_id"])
            self.assertEqual(result["queued"], 2)
            self.assertEqual([item["row_index"] for item in queued], [3, 5])


if __name__ == "__main__":
    unittest.main()
