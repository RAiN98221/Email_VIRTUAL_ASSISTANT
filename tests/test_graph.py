import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import db
from app.graph import GmailSmtpClient, SendVerification, active_credentials, html_to_plain_text


class GraphTests(unittest.TestCase):
    def test_active_credentials_prefers_active_account_over_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            self.assertEqual(active_credentials().source, "env")

            db.add_gmail_account("acct@gmail.com", "secret-app-pass", activate=True)
            credentials = active_credentials()
            self.assertEqual(credentials.source, "account")
            self.assertEqual(credentials.from_email, "acct@gmail.com")
            self.assertEqual(credentials.smtp_username, "acct@gmail.com")
            self.assertEqual(credentials.smtp_password, "secret-app-pass")
            self.assertEqual(credentials.imap_username, "acct@gmail.com")

            db.deactivate_gmail_accounts()
            self.assertEqual(active_credentials().source, "env")
    def test_send_mail_returns_message_id_and_verification(self):
        client = GmailSmtpClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.GmailSmtp", return_value=smtp),
            patch("app.graph.GmailSmtpSsl", return_value=smtp),
            patch.object(
                client,
                "verify_sent_mail",
                return_value=SendVerification("sent_mail_found", "found", '"[Gmail]/Sent Mail"'),
            ) as verify_sent_mail,
        ):
            result = client.send_mail("person@example.com", "Subject", "Body")

        smtp.login.assert_called_once()
        smtp.send_message.assert_called_once()
        verify_sent_mail.assert_called_once_with(result.message_id)
        self.assertTrue(result.smtp_accepted)
        self.assertEqual(result.verification.status, "sent_mail_found")

    def test_send_mail_attaches_extra_headers(self):
        client = GmailSmtpClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.GmailSmtp", return_value=smtp),
            patch("app.graph.GmailSmtpSsl", return_value=smtp),
            patch.object(client, "verify_sent_mail", return_value=SendVerification("skipped", "test")),
        ):
            client.send_mail(
                "person@example.com",
                "Subject",
                "Body",
                extra_headers={"X-Campaign-Id": "test-campaign"},
            )

        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["X-Campaign-Id"], "test-campaign")
        self.assertIsNotNone(message["Date"])
        self.assertIsNotNone(message["Reply-To"])

    def test_html_to_plain_text_preserves_link_url(self):
        html = (
            'Hi Sam,<br><br>Pick a time:<br>'
            '<a href="https://calendly.com/me?email=sam%40example.com" '
            'style="color:#fff;">Schedule a call</a><br><br>Thanks'
        )

        text = html_to_plain_text(html)

        self.assertIn("Schedule a call (https://calendly.com/me?email=sam%40example.com)", text)
        self.assertNotIn("<a", text)
        self.assertNotIn("style=", text)
        self.assertIn("Hi Sam,", text)

    def test_send_mail_html_sets_readable_plain_text_alternative(self):
        client = GmailSmtpClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        html_body = 'Hello<br><a href="https://calendly.com/me">Schedule a call</a>'

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.GmailSmtp", return_value=smtp),
            patch("app.graph.GmailSmtpSsl", return_value=smtp),
            patch.object(client, "verify_sent_mail", return_value=SendVerification("skipped", "test")),
        ):
            client.send_mail("person@example.com", "Subject", html_body, content_type="HTML")

        message = smtp.send_message.call_args.args[0]
        plain_part = message.get_body(preferencelist=("plain",))
        plain_text = plain_part.get_content()
        self.assertNotIn("This message contains HTML content.", plain_text)
        self.assertIn("Schedule a call (https://calendly.com/me)", plain_text)

    def test_parse_mailbox_name_keeps_quoted_sent_mail_with_spaces(self):
        client = GmailSmtpClient()
        raw = br'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"'

        self.assertEqual(client._parse_mailbox_name(raw), b'"[Gmail]/Sent Mail"')

    def test_imap_search_string_quotes_message_id(self):
        client = GmailSmtpClient()

        self.assertEqual(
            client._imap_search_string('<abc"def@example.com>'),
            '"<abc\\"def@example.com>"',
        )

    def test_parse_inbound_message_extracts_reply_fields(self):
        client = GmailSmtpClient()
        raw = (
            b"From: Person <person@example.com>\r\n"
            b"Subject: Re: Hello\r\n"
            b"Message-ID: <reply@example.com>\r\n"
            b"In-Reply-To: <sent@example.com>\r\n"
            b"Date: Mon, 01 Jun 2026 10:00:00 -0500\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Sounds good.\r\n"
        )

        reply = client._parse_inbound_message(raw)

        self.assertEqual(reply.message_id, "<reply@example.com>")
        self.assertEqual(reply.from_email, "person@example.com")
        self.assertEqual(reply.subject, "Re: Hello")
        self.assertEqual(reply.body, "Sounds good.")
        self.assertEqual(reply.references, ["<sent@example.com>"])

    def test_parse_inbound_message_converts_single_part_html_to_text(self):
        client = GmailSmtpClient()
        raw = (
            b"From: Noreply <noreply@example.com>\r\n"
            b"Subject: HTML message\r\n"
            b"Message-ID: <html-reply@example.com>\r\n"
            b"Date: Mon, 01 Jun 2026 10:00:00 -0500\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<!DOCTYPE html><html><head><style>body{font-size:12px}</style></head>"
            b"<body><p>Hello&nbsp;there</p><p>Readable reply.</p></body></html>\r\n"
        )

        reply = client._parse_inbound_message(raw)

        self.assertNotIn("<!DOCTYPE", reply.body)
        self.assertNotIn("font-size", reply.body)
        self.assertIn("Hello there", reply.body)
        self.assertIn("Readable reply.", reply.body)


if __name__ == "__main__":
    unittest.main()
