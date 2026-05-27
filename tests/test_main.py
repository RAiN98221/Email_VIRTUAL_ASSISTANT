import asyncio
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import db
from app.graph import SendResult, SendVerification
from app.main import QueueRequest, SendTestRequest, create_job, safe_upload_name, send_test, upload_csv_file


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
                daily_send_limit=12,
                interval_jitter_minutes=3,
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
            job = db.list_jobs()[0]
            self.assertEqual(job["daily_send_limit"], 12)
            self.assertEqual(job["interval_jitter_minutes"], 3)

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

    def test_send_test_returns_verification_result_without_queueing(self):
        result = SendResult(
            smtp_accepted=True,
            message_id="<test@example.com>",
            verification=SendVerification("sent_mail_found", "found", '"[Gmail]/Sent Mail"'),
        )
        with patch("app.main.mail_client") as mail_client:
            mail_client.return_value.send_mail.return_value = result
            response = send_test(SendTestRequest(to_email="person@example.com"))

        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["smtp_accepted"])
        self.assertEqual(response["result"]["verification"]["status"], "sent_mail_found")
        self.assertFalse(response["delivery_confirmed"])

    def test_send_test_rejects_invalid_email(self):
        with self.assertRaises(HTTPException):
            send_test(SendTestRequest(to_email="not-an-email"))

    def test_safe_upload_name_requires_csv(self):
        self.assertEqual(safe_upload_name("My Contacts.csv"), "My_Contacts.csv")
        with self.assertRaises(HTTPException):
            safe_upload_name("contacts.xlsx")

    def test_upload_csv_file_validates_and_imports(self):
        csv_content = (
            "first_name,last_name,email,phone,city,state,birth_date,age,gender\n"
            "Sam,Sample,sam@example.com,555,Austin,TX,2000-01-01,26,M\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            upload = UploadFile(filename="picked contacts.csv", file=BytesIO(csv_content))
            with patch("app.main.CSV_UPLOAD_DIR", Path(tmp)):
                result = asyncio.run(upload_csv_file(upload))

            self.assertEqual(result["count"], 1)
            self.assertTrue(result["file"]["name"].endswith("/picked_contacts.csv"))
            self.assertTrue((Path(tmp) / "picked_contacts.csv").exists())


if __name__ == "__main__":
    unittest.main()
