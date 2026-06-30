import asyncio
import hashlib
import hmac
import json
from io import BytesIO
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile
from starlette.requests import Request


def make_request(body: bytes, headers: dict | None = None) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {"type": "http", "method": "POST", "path": "/api/calendly/webhook", "headers": raw_headers}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)

from app import db
from app.graph import SendResult
from app.contacts import Contact
from app.main import (
    MailAccountRequest,
    PreviewRequest,
    QueueRequest,
    SchedulingSettingsRequest,
    SendTestRequest,
    SuppressionRequest,
    TemplateRequest,
    CalendlyWebhookSettingsRequest,
    CALENDLY_SIGNING_KEY,
    accounts,
    activate_account,
    add_account,
    available_csv_files,
    build_scheduling_link,
    calendly_button_html,
    calendly_bookings,
    calendly_webhook,
    deactivate_accounts,
    delete_account,
    build_preview,
    mark_calendly_bookings_read,
    update_calendly_webhook_settings,
    uses_calendly_button,
    verify_calendly_signature,
    scheduling_settings,
    update_scheduling_settings,
    create_job,
    create_suppression,
    delete_suppression,
    email_status_summary,
    safe_attachment_name,
    safe_upload_name,
    save_template,
    send_test,
    upload_attachments,
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

    def test_build_scheduling_link_prefills_name_and_email(self):
        contact = Contact(
            row_index=0, first_name="Jamie", last_name="Chen", email="jamie.chen@example.com",
            phone="", city="", state="", birth_date="", age="", gender="",
        )
        link = build_scheduling_link("https://calendly.com/me/intro", contact)
        self.assertIn("https://calendly.com/me/intro?", link)
        self.assertIn("name=Jamie+Chen", link)
        self.assertIn("email=jamie.chen%40example.com", link)

        self.assertEqual(build_scheduling_link("", contact), "")

        merged = build_scheduling_link("https://calendly.com/me/intro?utm_source=outreach", contact)
        self.assertIn("utm_source=outreach", merged)
        self.assertIn("name=Jamie+Chen", merged)

    @staticmethod
    def _booking_payload(uri: str = "https://api.calendly.com/scheduled_events/e1/invitees/i1", kind: str = "invitee.created") -> bytes:
        return json.dumps(
            {
                "event": kind,
                "payload": {
                    "name": "Ivan Gabel",
                    "email": "ivan@example.com",
                    "uri": uri,
                    "scheduled_event": {"name": "30 Minute Meeting", "start_time": "2026-07-01T15:00:00Z"},
                },
            }
        ).encode("utf-8")

    def test_verify_calendly_signature_matches_hmac(self):
        body = b'{"event":"invitee.created"}'
        key = "secret-key"
        digest = hmac.new(key.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_calendly_signature(key, f"t=1700000000,v1={digest}", body))
        self.assertFalse(verify_calendly_signature(key, "t=1700000000,v1=deadbeef", body))
        self.assertFalse(verify_calendly_signature(key, "", body))

    def test_calendly_webhook_records_booking_and_marks_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            result = asyncio.run(calendly_webhook(make_request(self._booking_payload())))
            self.assertEqual(result, {"ok": True, "recorded": True})

            listing = calendly_bookings()
            self.assertEqual(listing["unread"], 1)
            self.assertEqual(listing["bookings"][0]["invitee_name"], "Ivan Gabel")
            self.assertEqual(listing["bookings"][0]["event_name"], "30 Minute Meeting")

            # Duplicate delivery of the same invitee + kind is ignored.
            duplicate = asyncio.run(calendly_webhook(make_request(self._booking_payload())))
            self.assertEqual(duplicate["recorded"], False)
            self.assertEqual(calendly_bookings()["unread"], 1)

            mark_calendly_bookings_read()
            self.assertEqual(calendly_bookings()["unread"], 0)

    def test_calendly_webhook_ignores_unrelated_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            body = json.dumps({"event": "routing_form_submission.created", "payload": {}}).encode()
            result = asyncio.run(calendly_webhook(make_request(body)))
            self.assertEqual(result["ignored"], "routing_form_submission.created")
            self.assertEqual(calendly_bookings()["unread"], 0)

    def test_calendly_webhook_enforces_signature_when_key_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            update_calendly_webhook_settings(CalendlyWebhookSettingsRequest(signing_key="topsecret"))

            body = self._booking_payload()
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(calendly_webhook(make_request(body, {"Calendly-Webhook-Signature": "t=1,v1=bad"})))
            self.assertEqual(ctx.exception.status_code, 401)

            digest = hmac.new(b"topsecret", b"1700000000." + body, hashlib.sha256).hexdigest()
            ok = asyncio.run(
                calendly_webhook(make_request(body, {"Calendly-Webhook-Signature": f"t=1700000000,v1={digest}"}))
            )
            self.assertEqual(ok["recorded"], True)

    def test_scheduling_settings_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            self.assertEqual(scheduling_settings(), {"scheduling_url": ""})
            saved = update_scheduling_settings(SchedulingSettingsRequest(scheduling_url="https://calendly.com/me/intro"))
            self.assertEqual(saved["scheduling_url"], "https://calendly.com/me/intro")
            self.assertEqual(scheduling_settings()["scheduling_url"], "https://calendly.com/me/intro")

            with self.assertRaises(HTTPException) as invalid:
                update_scheduling_settings(SchedulingSettingsRequest(scheduling_url="calendly.com/me"))
            self.assertEqual(invalid.exception.status_code, 400)

            cleared = update_scheduling_settings(SchedulingSettingsRequest(scheduling_url="   "))
            self.assertEqual(cleared["scheduling_url"], "")

    def test_calendly_button_html_is_safe_anchor(self):
        html = calendly_button_html("https://calendly.com/me/intro?email=a%40b.com")
        self.assertIn('<a href="https://calendly.com/me/intro?email=a%40b.com"', html)
        self.assertIn("Schedule a call", html)
        self.assertIn("display:inline-block", html)
        self.assertTrue(uses_calendly_button("Book: {{calendly_button}}"))
        self.assertTrue(uses_calendly_button("Book: {{calendly_link}}"))  # link variable also renders the button
        self.assertFalse(uses_calendly_button("Book: {{first_name}}"))

    def test_build_preview_renders_calendly_button_as_html_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            db.set_app_setting("scheduling_url", "https://calendly.com/me/intro")
            payload = PreviewRequest(
                subject="Hi {{first_name}}",
                body="Let's talk.\n{{calendly_button}}\nThanks & regards",
                csv_file="test_contacts.csv",
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                preview = build_preview(payload)
            self.assertEqual(preview["content_type"], "HTML")
            body = preview["rows"][0]["body"]
            self.assertIn('<a href="https://calendly.com/me/intro?', body)
            self.assertIn("Schedule a call", body)
            self.assertNotIn("{{calendly_button}}", body)
            self.assertIn("<br>", body)  # newlines preserved as HTML
            self.assertIn("Thanks &amp; regards", body)  # surrounding text is escaped

    def test_build_preview_plain_text_when_button_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                subject="Hi {{first_name}}",
                body="Plain body with no scheduling variable.",
                csv_file="test_contacts.csv",
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                preview = build_preview(payload)
            self.assertEqual(preview["content_type"], "Text")
            self.assertNotIn("<a href", preview["rows"][0]["body"])

    def test_build_preview_renders_calendly_link_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            db.set_app_setting("scheduling_url", "https://calendly.com/me/intro")
            payload = PreviewRequest(
                subject="Hi {{first_name}}",
                body="Book a call: {{calendly_link}}",
                csv_file="test_contacts.csv",
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                preview = build_preview(payload)
            first = preview["rows"][0]
            # {{calendly_link}} renders the same scheduling button as {{calendly_button}}.
            self.assertEqual(preview["content_type"], "HTML")
            self.assertIn('<a href="https://calendly.com/me/intro?', first["body"])
            self.assertIn("email=", first["body"])
            self.assertIn("Schedule a call", first["body"])
            self.assertNotIn("{{calendly_link}}", first["body"])

    def test_account_endpoints_manage_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            added = add_account(MailAccountRequest(from_email="Outreach@MyDomain.com", smtp_username="login-1", smtp_password="brevo key one", verify=False))
            self.assertEqual(added["account"]["email"], "outreach@mydomain.com")
            self.assertTrue(added["account"]["is_active"])

            with self.assertRaises(HTTPException) as duplicate:
                add_account(MailAccountRequest(from_email="outreach@mydomain.com", smtp_username="login-1", smtp_password="brevokeyone", verify=False))
            self.assertEqual(duplicate.exception.status_code, 409)

            with self.assertRaises(HTTPException) as invalid:
                add_account(MailAccountRequest(from_email="not-an-email", smtp_username="login-1", smtp_password="brevokeyone", verify=False))
            self.assertEqual(invalid.exception.status_code, 400)

            second = add_account(MailAccountRequest(from_email="backup@mydomain.com", smtp_username="login-2", smtp_password="brevokeytwo", verify=False, activate=False))
            self.assertFalse(second["account"]["is_active"])

            activated = activate_account(second["account"]["id"])
            self.assertTrue(activated["account"]["is_active"])
            listing = accounts()
            active = [account for account in listing["accounts"] if account["is_active"]]
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["email"], "backup@mydomain.com")

            deactivate_accounts()
            listing = accounts()
            self.assertFalse(any(account["is_active"] for account in listing["accounts"]))

            self.assertEqual(delete_account(second["account"]["id"]), {"deleted": True, "id": second["account"]["id"]})
            with self.assertRaises(HTTPException) as missing:
                delete_account(second["account"]["id"])
            self.assertEqual(missing.exception.status_code, 404)

    def test_add_account_verifies_credentials_with_smtp(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            with patch("app.main.mail_client") as mock_client:
                mock_client.return_value.verify_login.side_effect = RuntimeError("Username and Password not accepted")
                with self.assertRaises(HTTPException) as rejected:
                    add_account(
                        MailAccountRequest(
                            provider="smtp",
                            from_email="real@mydomain.com",
                            smtp_host="smtp.mailhost.com",
                            smtp_username="real@mydomain.com",
                            smtp_password="wrong password 1234",
                        )
                    )
            self.assertEqual(rejected.exception.status_code, 400)
            self.assertIn("rejected", rejected.exception.detail)
            self.assertEqual(accounts()["accounts"], [])

            with patch("app.main.mail_client") as mock_client:
                added = add_account(
                    MailAccountRequest(
                        provider="smtp",
                        from_email="real@mydomain.com",
                        smtp_host="smtp.mailhost.com",
                        smtp_username="real@mydomain.com",
                        smtp_password="abcd efgh ijkl mnop",
                    )
                )
            mock_client.return_value.verify_login.assert_called_once_with(
                "real@mydomain.com",
                "abcdefghijklmnop",
                smtp_host="smtp.mailhost.com",
                smtp_port=587,
                smtp_security="starttls",
            )
            self.assertTrue(added["account"]["is_active"])
            self.assertEqual(added["account"]["provider"], "smtp")

    def test_add_account_accepts_brevo_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            with patch("app.main.mail_client") as mock_client:
                added = add_account(
                    MailAccountRequest(
                        provider="brevo",
                        from_email="Sender@MyDomain.com",
                        from_name="Sender Name",
                        smtp_username="brevo-login@smtp-brevo.com",
                        smtp_password="brevo-smtp-key",
                    )
                )
            mock_client.return_value.verify_login.assert_called_once_with(
                "brevo-login@smtp-brevo.com",
                "brevo-smtp-key",
                smtp_host="smtp-relay.brevo.com",
                smtp_port=587,
                smtp_security="starttls",
            )
            account = added["account"]
            self.assertEqual(account["provider"], "brevo")
            self.assertEqual(account["from_email"], "sender@mydomain.com")
            self.assertEqual(account["from_name"], "Sender Name")
            self.assertEqual(account["smtp_host"], "smtp-relay.brevo.com")
            self.assertTrue(account["is_active"])

    def test_add_account_brevo_requires_smtp_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            with self.assertRaises(HTTPException) as missing_login:
                add_account(
                    MailAccountRequest(
                        provider="brevo",
                        from_email="sender@mydomain.com",
                        smtp_password="brevo-smtp-key",
                        verify=False,
                    )
                )
            self.assertEqual(missing_login.exception.status_code, 400)

    def test_queue_request_rejects_invalid_timezone(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            QueueRequest(subject="Hi", body="Hello", timezone="Not/AZone")

    def test_queue_request_rejects_out_of_range_clock_time(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            QueueRequest(subject="Hi", body="Hello", business_start="99:00")

    def test_queue_request_accepts_valid_schedule(self):
        payload = QueueRequest(
            subject="Hi", body="Hello", timezone="America/New_York",
            business_start="08:30", business_end="18:00",
        )
        self.assertEqual(payload.timezone, "America/New_York")

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

    def test_create_job_rotates_templates_round_robin(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            variant_a = db.save_template("Variant A", "A {{first_name}}", "Body A {{first_name}}")
            variant_b = db.save_template("Variant B", "B {{first_name}}", "Body B {{first_name}}")
            payload = QueueRequest(
                csv_file="test_contacts.csv",
                subject="Inline {{first_name}}",
                body="Inline body",
                template_ids=[variant_a["id"], variant_b["id"]],
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                result = create_job(payload)
            queued = db.list_queue(result["job_id"])
            self.assertEqual(
                [item["subject"] for item in queued],
                ["A Jamie", "B Alex", "A Pat", "B Sam"],
            )
            self.assertEqual(
                [item["template_name"] for item in queued],
                ["Variant A", "Variant B", "Variant A", "Variant B"],
            )
            job = db.list_jobs()[0]
            self.assertEqual(job["template_rotation"], '["Variant A", "Variant B"]')

    def test_build_preview_rejects_unknown_rotation_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            payload = PreviewRequest(
                csv_file="test_contacts.csv",
                subject="Hi {{first_name}}",
                body="Hello",
                template_ids=["missing-a", "missing-b"],
            )
            with self.assertRaises(HTTPException) as ctx:
                build_preview(payload)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_single_template_selection_keeps_inline_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            variant_a = db.save_template("Variant A", "A {{first_name}}", "Body A")
            payload = PreviewRequest(
                csv_file="test_contacts.csv",
                subject="Inline {{first_name}}",
                body="Inline body",
                template_ids=[variant_a["id"]],
                exclude_company_emails=False,
                gender_filter="all",
            )
            with patch("app.main.available_csv_files") as available_csv_files:
                available_csv_files.return_value = self.write_contacts_csv(tmp)
                preview = build_preview(payload)
            subjects = [row["subject"] for row in preview["rows"]]
            self.assertEqual(subjects, ["Inline Jamie", "Inline Alex", "Inline Pat", "Inline Sam"])
            self.assertTrue(all(row["template_name"] is None for row in preview["rows"]))

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

    def test_send_test_returns_result_without_queueing(self):
        result = SendResult(
            smtp_accepted=True,
            message_id="<test@example.com>",
        )
        with patch("app.main.mail_client") as mail_client:
            mail_client.return_value.send_mail.return_value = result
            response = send_test(SendTestRequest(to_email="person@example.com"))

        self.assertTrue(response["ok"])
        self.assertTrue(response["result"]["smtp_accepted"])
        self.assertEqual(response["result"]["message_id"], "<test@example.com>")
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
