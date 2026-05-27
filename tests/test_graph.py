import unittest
from unittest.mock import MagicMock, patch

from app.graph import GmailSmtpClient, SendVerification


class GraphTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
