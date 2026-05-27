from __future__ import annotations

import smtplib
import socket
import ssl
import time
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import make_msgid
import imaplib
import re
from typing import Any

from .logging_config import get_logger
from .settings import settings


PLACEHOLDER_SMTP_VALUES = {"", "your-gmail-address@gmail.com", "your-google-app-password"}
logger = get_logger(__name__)


class MailNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class SendVerification:
    status: str
    detail: str
    mailbox: str | None = None


@dataclass(frozen=True)
class SendResult:
    smtp_accepted: bool
    message_id: str
    verification: SendVerification

    def as_dict(self) -> dict[str, Any]:
        return {
            "smtp_accepted": self.smtp_accepted,
            "message_id": self.message_id,
            "verification": asdict(self.verification),
            "meaning": (
                "SMTP accepted the message and Gmail Sent Mail contains the Message-ID."
                if self.verification.status == "sent_mail_found"
                else "SMTP accepted the message; recipient inbox delivery is not confirmed."
            ),
        }


class SmtpConnectMixin:
    def _get_socket(self, host: str, port: int, timeout: float):
        connect_host = settings.smtp_connect_host.strip() or host
        return socket.create_connection((connect_host, port), timeout)


class GmailSmtp(SmtpConnectMixin, smtplib.SMTP):
    pass


class GmailSmtpSsl(SmtpConnectMixin, smtplib.SMTP_SSL):
    def _get_socket(self, host: str, port: int, timeout: float):
        raw_socket = SmtpConnectMixin._get_socket(self, host, port, timeout)
        context = self.context or ssl.create_default_context()
        return context.wrap_socket(raw_socket, server_hostname=host)


class GmailSmtpClient:
    def is_configured(self) -> bool:
        return (
            settings.smtp_host.strip() not in PLACEHOLDER_SMTP_VALUES
            and settings.smtp_username.strip() not in PLACEHOLDER_SMTP_VALUES
            and settings.smtp_password.strip() not in PLACEHOLDER_SMTP_VALUES
            and settings.from_email.strip() not in PLACEHOLDER_SMTP_VALUES
        )

    def is_imap_configured(self) -> bool:
        return (
            settings.imap_host.strip() not in PLACEHOLDER_SMTP_VALUES
            and settings.imap_username.strip() not in PLACEHOLDER_SMTP_VALUES
            and settings.imap_password.strip() not in PLACEHOLDER_SMTP_VALUES
        )

    def auth_status(self) -> dict[str, Any]:
        return {
            "provider": "gmail",
            "configured": self.is_configured(),
            "authenticated": self.is_configured(),
            "account": settings.from_email or settings.smtp_username or None,
            "connect_host": settings.smtp_connect_host or settings.smtp_host,
            "sent_mail_verification": {
                "enabled": settings.verify_sent_mail,
                "configured": self.is_imap_configured(),
                "host": settings.imap_host,
                "timeout_seconds": settings.verify_sent_timeout_seconds,
            },
        }

    def send_mail(self, to_email: str, subject: str, body: str, content_type: str = "Text") -> SendResult:
        if not self.is_configured():
            raise MailNotConfigured("Set SMTP_USERNAME, SMTP_PASSWORD, and FROM_EMAIL in .env first.")

        message_id = make_msgid(domain=(settings.from_email.split("@")[-1] or "localhost"))
        message = EmailMessage()
        message["From"] = settings.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message["Message-ID"] = message_id
        if content_type.lower() == "html":
            message.set_content("This message contains HTML content.")
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        logger.info(
            "smtp_send_start host=%s connect_host=%s port=%s from=%s to=%s content_type=%s",
            settings.smtp_host,
            settings.smtp_connect_host or settings.smtp_host,
            settings.smtp_port,
            settings.from_email,
            to_email,
            content_type,
        )
        try:
            if settings.smtp_port == 465:
                smtp_context = GmailSmtpSsl(settings.smtp_host, settings.smtp_port, timeout=60)
            else:
                smtp_context = GmailSmtp(settings.smtp_host, settings.smtp_port, timeout=60)
            with smtp_context as smtp:
                logger.info("smtp_connected host=%s port=%s to=%s", settings.smtp_host, settings.smtp_port, to_email)
                smtp.ehlo()
                if settings.smtp_port != 465:
                    smtp.starttls()
                    smtp.ehlo()
                    logger.info("smtp_tls_ready to=%s", to_email)
                smtp.login(settings.smtp_username, settings.smtp_password)
                logger.info("smtp_login_ok username=%s to=%s", settings.smtp_username, to_email)
                smtp.send_message(message)
            logger.info("smtp_send_ok to=%s subject=%r", to_email, subject)
        except Exception:
            logger.exception("smtp_send_failed host=%s port=%s to=%s", settings.smtp_host, settings.smtp_port, to_email)
            raise

        verification = self.verify_sent_mail(message_id)
        return SendResult(smtp_accepted=True, message_id=message_id, verification=verification)

    def verify_sent_mail(self, message_id: str) -> SendVerification:
        if not settings.verify_sent_mail:
            return SendVerification("skipped", "Sent Mail verification is disabled by VERIFY_SENT_MAIL.")
        if not self.is_imap_configured():
            return SendVerification("skipped", "Set IMAP_USERNAME and IMAP_PASSWORD to verify Gmail Sent Mail.")

        deadline = time.monotonic() + max(settings.verify_sent_timeout_seconds, 1)
        last_error = ""
        while time.monotonic() <= deadline:
            try:
                found = self._find_message_in_sent_mail(message_id)
                if found:
                    return SendVerification(
                        "sent_mail_found",
                        "Gmail Sent Mail contains the sent Message-ID.",
                        found,
                    )
                last_error = "Message-ID was not visible in Gmail Sent Mail yet."
            except Exception as exc:
                last_error = str(exc)
                logger.exception("imap_sent_mail_verify_failed message_id=%s", message_id)
            time.sleep(max(settings.verify_sent_poll_seconds, 1))

        logger.warning("imap_sent_mail_not_found message_id=%s detail=%s", message_id, last_error)
        return SendVerification("sent_mail_not_found", last_error)

    def _find_message_in_sent_mail(self, message_id: str) -> str | None:
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=30) as imap:
            imap.login(settings.imap_username, settings.imap_password)
            for mailbox in self._sent_mailboxes(imap):
                status, _ = imap.select(mailbox, readonly=True)
                if status != "OK":
                    continue
                status, data = imap.search(None, "HEADER", "Message-ID", self._imap_search_string(message_id))
                if status == "OK" and data and data[0].strip():
                    return mailbox.decode("utf-8", errors="replace")
            imap.logout()
        return None

    def _sent_mailboxes(self, imap: imaplib.IMAP4_SSL) -> list[bytes]:
        status, data = imap.list()
        discovered: list[bytes] = []
        if status == "OK" and data:
            for raw in data:
                if not raw:
                    continue
                lower = raw.lower()
                if b"\\sent" not in lower and b"sent mail" not in lower:
                    continue
                mailbox = self._parse_mailbox_name(raw)
                if mailbox:
                    discovered.append(mailbox)
        fallback = [b'"[Gmail]/Sent Mail"', b'"[Google Mail]/Sent Mail"', b'"Sent"', b"Sent"]
        return discovered + [mailbox for mailbox in fallback if mailbox not in discovered]

    def _parse_mailbox_name(self, raw: bytes) -> bytes | None:
        match = re.search(rb'("[^"]+"|[^\s]+)$', raw)
        if not match:
            return None
        return match.group(1).strip()

    def _imap_search_string(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def mail_client() -> GmailSmtpClient:
    return GmailSmtpClient()
