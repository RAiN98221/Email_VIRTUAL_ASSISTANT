import asyncio
from io import BytesIO
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app import db
from app.graph import SendResult, SendVerification
from app.main import (
    PreviewRequest,
    QueueRequest,
    ReplySyncRequest,
    SendTestRequest,
    SuppressionRequest,
    TemplateRequest,
    available_csv_files,
    build_preview,
    create_job,
    create_suppression,
    delete_suppression,
    email_status_summary,
    safe_attachment_name,
    safe_upload_name,
    save_template,
    send_test,
    sync_replies,
    upload_attachments,
    unsubscribe_post,
    upload_csv_file,
)


class MainTests(unittest.TestCase):
    SAMPLE_CONTACTS_CSV = (
        "first_name,last_name,email,phone,city,state,age,gender\n"
        "Jamie,Chen,jamie.chen@example.com,555-0100,Austin,TX,32,F\n"
        "Alex,Kim,alex.kim@example.com,555-0101,Austin,TX,33,M\n"
        "Pat,Lee,pat.lee@example.com,555-0102,Austin,TX,34,F\n"
        "Sam,Roy,sam.roy@example.com,555-0103,Austin,TX,35,M\n"
    )

    def write_contacts_csv(self, tmp: str) -> list[dict]:
        csv_path = Path(tmp) / "test_contacts.csv"
        csv_path.write_text(self.SAMPLE_CONTACTS_CSV, encoding="utf-8")
        return [{"name": "test_contacts.csv", "path": str(csv_path), "default": False}]

    def test_create_job_honors_send_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = QueueRequest(
                campaign_name="Caregiver Outreach",
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                send_limit=2,
                exclude_company_emails=False,
                gender_filter="all",
                daily_send_limit=12,
                interval_jitter_minutes=3,
                max_failures=4,
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                result = create_job(payload)
            self.assertEqual(result["queued"], 2)
            self.assertEqual(len(db.list_queue(result["job_id"])), 2)
            job = db.list_jobs()[0]
            self.assertEqual(job["daily_send_limit"], 12)
            self.assertEqual(job["campaign_name"], "Caregiver Outreach")
            self.assertEqual(job["interval_jitter_minutes"], 3)
            self.assertEqual(job["max_failures"], 4)
            self.assertEqual(job["auto_pause_on_failure"], 1)

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
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                result = create_job(payload)
            queued = db.list_queue(result["job_id"])
            self.assertEqual(result["queued"], 2)
            self.assertEqual([item["row_index"] for item in queued], [3, 5])

    def test_create_job_stores_selected_attachments(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            attachment = Path(tmp) / "overview.pdf"
            attachment.write_bytes(b"pdf")
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = QueueRequest(
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                selected_row_indexes=[3],
                attachment_ids=["uploaded_attachments/overview.pdf"],
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files, patch("app.main.available_attachments") as available_attachments:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                available_attachments.return_value = [
                    {
                        "id": "uploaded_attachments/overview.pdf",
                        "name": "overview.pdf",
                        "size": 3,
                        "path": str(attachment),
                    }
                ]
                result = create_job(payload)

            self.assertEqual(result["queued"], 1)
            self.assertEqual(db.list_jobs()[0]["attachment_files"], '["uploaded_attachments/overview.pdf"]')

    def test_email_status_summary_endpoint_returns_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            response = email_status_summary()

            self.assertEqual(response["total"], 0)
            self.assertIn({"key": "sent", "label": "Sent", "count": 0}, response["statuses"])
            self.assertIn({"key": "replied", "label": "Replied", "count": 0}, response["statuses"])

    def test_available_csv_files_only_lists_default_and_imported_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default_csv = root / "default_contacts.csv"
            root_extra = root / "test_contacts.csv"
            uploaded_dir = root / "uploaded_csv"
            uploaded_csv = uploaded_dir / "imported_contacts.csv"
            default_csv.write_text("email\nperson@example.com\n", encoding="utf-8")
            root_extra.write_text("email\nhelper@example.com\n", encoding="utf-8")
            uploaded_dir.mkdir()
            uploaded_csv.write_text("email\nimported@example.com\n", encoding="utf-8")

            with patch("app.main.ROOT_DIR", root), patch("app.main.CSV_UPLOAD_DIR", uploaded_dir), patch(
                "app.main.settings", SimpleNamespace(default_csv_path=default_csv)
            ):
                files = available_csv_files()

            names = [file["name"] for file in files]
            self.assertEqual(names, ["default_contacts.csv", "uploaded_csv/imported_contacts.csv"])
            self.assertNotIn("test_contacts.csv", names)

    def test_save_template_endpoint_persists_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            response = save_template(
                TemplateRequest(name="AI Outreach", subject="Hi {{first_name}}", body="Hello")
            )

            self.assertEqual(response["template"]["name"], "AI Outreach")
            self.assertEqual(db.list_templates()[0]["subject"], "Hi {{first_name}}")

    def test_sync_replies_skips_senders_not_in_selected_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            csv_path = Path(tmp) / "contacts.csv"
            csv_path.write_text(
                "first_name,last_name,email,phone,city,state,birth_date,age,gender\n"
                "Known,Person,known@example.com,555,Austin,TX,1990-01-01,30,F\n",
                encoding="utf-8",
            )
            mail = SimpleNamespace(
                fetch_inbound_replies=lambda limit=15: [
                    SimpleNamespace(
                        message_id="<known@example.com>",
                        from_email="known@example.com",
                        subject="Known reply",
                        body="Interested",
                        received_at="2026-06-01T10:00:00+00:00",
                        references=[],
                    ),
                    SimpleNamespace(
                        message_id="<noise@example.com>",
                        from_email="newsletter@example.com",
                        subject="Newsletter",
                        body="Noise",
                        received_at="2026-06-01T10:01:00+00:00",
                        references=[],
                    ),
                ]
            )
            with patch("app.main.available_csv_files") as available_csv_files, patch("app.main.mail_client", return_value=mail):
                available_csv_files.return_value = [
                    {"name": "contacts.csv", "path": str(csv_path), "default": False}
                ]
                result = sync_replies(ReplySyncRequest(csv_file="contacts.csv"))

            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["replies"][0]["from_email_norm"], "known@example.com")
            self.assertEqual(len(db.list_replies()), 1)

    def test_preview_excludes_suppressed_contacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            db.suppress_email(
                "jamie.chen@example.com",
                "jamie.chen@example.com",
                "unsubscribed",
                "unsubscribe_link",
                "test",
            )
            payload = PreviewRequest(
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                result = build_preview(payload)

            row = next(row for row in result["rows"] if row["email_norm"] == "jamie.chen@example.com")
            self.assertFalse(row["sendable"])
            self.assertTrue(row["suppressed"])
            self.assertIn("suppressed_unsubscribed", row["errors"])
            self.assertEqual(result["summary"]["suppressed"], 1)

    def test_preview_excludes_company_emails_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            csv_path = Path(tmp) / "contacts.csv"
            csv_path.write_text(
                "first_name,last_name,email,phone,city,state,age,gender\n"
                "Personal,Person,personal@gmail.com,555,Austin,TX,32,M\n"
                "Company,Person,admin@alayacare.com,555,Austin,TX,32,M\n",
                encoding="utf-8",
            )
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                csv_file="contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = [
                    {"name": "contacts.csv", "path": str(csv_path), "default": False}
                ]
                result = build_preview(payload)

            rows = {row["email_norm"]: row for row in result["rows"]}
            self.assertTrue(rows["personal@gmail.com"]["sendable"])
            self.assertFalse(rows["admin@alayacare.com"]["sendable"])
            self.assertIn("company_email", rows["admin@alayacare.com"]["errors"])
            self.assertEqual(result["summary"]["company_filtered"], 1)

    def test_preview_filters_to_male_contacts_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            csv_path = Path(tmp) / "contacts.csv"
            csv_path.write_text(
                "first_name,last_name,email,phone,city,state,age,gender\n"
                "Male,Person,male@gmail.com,555,Austin,TX,32,M\n"
                "Female,Person,female@gmail.com,555,Austin,TX,32,F\n"
                "Unknown,Person,unknown@gmail.com,555,Austin,TX,32,\n",
                encoding="utf-8",
            )
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                csv_file="contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                exclude_company_emails=False,
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = [
                    {"name": "contacts.csv", "path": str(csv_path), "default": False}
                ]
                result = build_preview(payload)

            rows = {row["email_norm"]: row for row in result["rows"]}
            self.assertTrue(rows["male@gmail.com"]["sendable"])
            self.assertIn("gender_filtered", rows["female@gmail.com"]["errors"])
            self.assertIn("gender_filtered", rows["unknown@gmail.com"]["errors"])
            self.assertEqual(result["summary"]["gender_filtered"], 2)

    def test_preview_applies_optional_age_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            csv_path = Path(tmp) / "contacts.csv"
            csv_path.write_text(
                "first_name,last_name,email,phone,city,state,age,gender\n"
                "Young,Person,young@example.com,555,Austin,TX,22,F\n"
                "Target,Person,target@example.com,555,Austin,TX,32,F\n"
                "Older,Person,older@example.com,555,Austin,TX,51,F\n"
                "Missing,Person,missing@example.com,555,Austin,TX,,F\n",
                encoding="utf-8",
            )
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                csv_file="contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                exclude_company_emails=False,
                gender_filter="all",
                age_min=25,
                age_max=44,
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = [
                    {"name": "contacts.csv", "path": str(csv_path), "default": False}
                ]
                result = build_preview(payload)

            rows = {row["email_norm"]: row for row in result["rows"]}
            self.assertIn("outside_age_range", rows["young@example.com"]["errors"])
            self.assertTrue(rows["target@example.com"]["sendable"])
            self.assertIn("outside_age_range", rows["older@example.com"]["errors"])
            self.assertTrue(rows["missing@example.com"]["sendable"])
            self.assertEqual(result["summary"]["age_filtered"], 2)

    def test_preview_supports_manual_recipients_without_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                csv_file=None,
                subject="Hi {{first_name}}",
                body="Hello {{first_name}}",
                exclude_company_emails=False,
                manual_only=True,
                manual_recipients=[
                    "Ada Lovelace <ada@example.com>",
                    "grace.hopper@gmail.com",
                ],
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = []
                result = build_preview(payload)

            rows = {row["email_norm"]: row for row in result["rows"]}
            self.assertEqual(result["summary"]["total"], 2)
            self.assertTrue(rows["ada@example.com"]["sendable"])
            self.assertEqual(rows["ada@example.com"]["first_name"], "Ada")
            self.assertTrue(rows["grace.hopper@gmail.com"]["sendable"])
            self.assertEqual(rows["grace.hopper@gmail.com"]["first_name"], "Grace")

    def test_unsubscribe_post_records_suppression(self):
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
            job_id = db.create_job('Test Campaign', [item], 10, 0, 25, 3, True, "09:00", "17:00", "America/Chicago", False, "Text")
            token = db.list_queue(job_id)[0]["unsubscribe_token"]

            response = unsubscribe_post(token)

            self.assertTrue(response["ok"])
            self.assertEqual(db.suppressed_emails()["person@example.com"]["reason"], "unsubscribed")

    def test_create_and_delete_manual_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            created = create_suppression(
                SuppressionRequest(
                    email="Person@Example.com",
                    reason="manual",
                    note="asked elsewhere",
                )
            )
            suppressions = db.suppressed_emails()
            deleted = delete_suppression("person@example.com")

            self.assertTrue(created["ok"])
            self.assertEqual(suppressions["person@example.com"]["source"], "manual")
            self.assertEqual(suppressions["person@example.com"]["note"], "asked elsewhere")
            self.assertTrue(deleted["ok"])
            self.assertEqual(db.suppressed_emails(), {})

    def test_create_suppression_rejects_invalid_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            with self.assertRaises(HTTPException):
                create_suppression(SuppressionRequest(email="not-an-email"))

    def test_delete_suppression_raises_for_missing_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            with self.assertRaises(HTTPException):
                delete_suppression("missing@example.com")

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

    def test_safe_attachment_name_sanitizes_general_files(self):
        self.assertEqual(safe_attachment_name("My deck final.pdf"), "My_deck_final.pdf")
        self.assertEqual(safe_attachment_name("../photo 1.PNG"), "photo_1.png")

    def test_upload_csv_file_validates_and_imports(self):
        csv_content = (
            "first_name,last_name,email,phone,city,state,gender\n"
            "Sam,Sample,sam@example.com,555,Austin,TX,M\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            upload = UploadFile(filename="picked contacts.csv", file=BytesIO(csv_content))
            with patch("app.main.CSV_UPLOAD_DIR", Path(tmp)):
                result = asyncio.run(upload_csv_file(upload))

            self.assertEqual(result["count"], 1)
            self.assertTrue(result["file"]["name"].endswith("/picked_contacts.csv"))
            self.assertTrue((Path(tmp) / "picked_contacts.csv").exists())

    def test_upload_attachments_accepts_multiple_files(self):
        uploads = [
            UploadFile(filename="profile image.png", file=BytesIO(b"image")),
            UploadFile(filename="one pager.pdf", file=BytesIO(b"pdf")),
        ]
        try:
            with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
                with patch("app.main.ATTACHMENT_UPLOAD_DIR", Path(tmp)):
                    result = asyncio.run(upload_attachments(uploads))

                for upload in uploads:
                    upload.file.close()
                self.assertEqual([file["name"] for file in result["files"]], ["profile_image.png", "one_pager.pdf"])
                self.assertTrue((Path(tmp) / "profile_image.png").exists())
                self.assertTrue((Path(tmp) / "one_pager.pdf").exists())
        finally:
            for upload in uploads:
                upload.file.close()


if __name__ == "__main__":
    unittest.main()
