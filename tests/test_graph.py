import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import db
from app.graph import MailClient, active_credentials, html_to_plain_text


def _add_brevo_account(activate: bool = True) -> dict:
    return db.add_mail_account(
        from_email="sender@mydomain.com",
        secret="brevo-key",
        provider="brevo",
        smtp_host="smtp-relay.brevo.com",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="brevo-login",
        from_name="Sender Name",
        activate=activate,
    )


class GraphTests(unittest.TestCase):
    def test_active_credentials_prefers_active_account_over_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            self.assertEqual(active_credentials().source, "env")

            _add_brevo_account(activate=True)
            credentials = active_credentials()
            self.assertEqual(credentials.source, "account")
            self.assertEqual(credentials.from_email, "sender@mydomain.com")
            self.assertEqual(credentials.smtp_username, "brevo-login")
            self.assertEqual(credentials.smtp_password, "brevo-key")

            db.deactivate_mail_accounts()
            self.assertEqual(active_credentials().source, "env")

    def test_active_credentials_loads_brevo_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)

            _add_brevo_account(activate=True)
            credentials = active_credentials()
            self.assertEqual(credentials.provider, "brevo")
            self.assertEqual(credentials.smtp_host, "smtp-relay.brevo.com")
            self.assertEqual(credentials.smtp_port, 587)
            self.assertEqual(credentials.smtp_security, "starttls")
            self.assertEqual(credentials.smtp_username, "brevo-login")
            self.assertEqual(credentials.from_email, "sender@mydomain.com")
            self.assertEqual(credentials.from_name, "Sender Name")
            db.deactivate_mail_accounts()

    def test_send_mail_uses_active_account_transport_and_from_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            db.init_db(db_path)
            db.configure_database(db_path)
            _add_brevo_account(activate=True)
            client = MailClient()
            smtp = MagicMock()
            smtp.__enter__.return_value = smtp

            with patch("app.graph._open_smtp", return_value=smtp) as open_smtp:
                result = client.send_mail("person@example.com", "Subject", "Body")

            open_smtp.assert_called_once_with("smtp-relay.brevo.com", 587, "starttls", timeout=60)
            smtp.login.assert_called_once_with("brevo-login", "brevo-key")
            message = smtp.send_message.call_args.args[0]
            self.assertEqual(message["From"], "Sender Name <sender@mydomain.com>")
            self.assertTrue(result.smtp_accepted)
            db.deactivate_mail_accounts()

    def test_send_mail_returns_message_id(self):
        client = MailClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.SmtpPlain", return_value=smtp),
            patch("app.graph.SmtpSsl", return_value=smtp),
        ):
            result = client.send_mail("person@example.com", "Subject", "Body")

        smtp.login.assert_called_once()
        smtp.send_message.assert_called_once()
        self.assertTrue(result.smtp_accepted)
        self.assertTrue(result.message_id)

    def test_send_mail_attaches_extra_headers(self):
        client = MailClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.SmtpPlain", return_value=smtp),
            patch("app.graph.SmtpSsl", return_value=smtp),
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
        client = MailClient()
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        html_body = 'Hello<br><a href="https://calendly.com/me">Schedule a call</a>'

        with (
            patch.object(client, "is_configured", return_value=True),
            patch("app.graph.SmtpPlain", return_value=smtp),
            patch("app.graph.SmtpSsl", return_value=smtp),
        ):
            client.send_mail("person@example.com", "Subject", html_body, content_type="HTML")

        message = smtp.send_message.call_args.args[0]
        plain_part = message.get_body(preferencelist=("plain",))
        plain_text = plain_part.get_content()
        self.assertNotIn("This message contains HTML content.", plain_text)
        self.assertIn("Schedule a call (https://calendly.com/me)", plain_text)


if __name__ == "__main__":
    unittest.main()
