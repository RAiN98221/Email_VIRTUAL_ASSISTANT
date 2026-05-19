from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Any

from .logging_config import get_logger
from .settings import settings


PLACEHOLDER_SMTP_VALUES = {"", "your-gmail-address@gmail.com", "your-google-app-password"}
logger = get_logger(__name__)


class MailNotConfigured(RuntimeError):
    pass


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

    def auth_status(self) -> dict[str, Any]:
        return {
            "provider": "gmail",
            "configured": self.is_configured(),
            "authenticated": self.is_configured(),
            "account": settings.from_email or settings.smtp_username or None,
            "connect_host": settings.smtp_connect_host or settings.smtp_host,
        }

    def send_mail(self, to_email: str, subject: str, body: str, content_type: str = "Text") -> str | None:
        if not self.is_configured():
            raise MailNotConfigured("Set SMTP_USERNAME, SMTP_PASSWORD, and FROM_EMAIL in .env first.")

        message = EmailMessage()
        message["From"] = settings.from_email
        message["To"] = to_email
        message["Subject"] = subject
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
        return None


def mail_client() -> GmailSmtpClient:
    return GmailSmtpClient()
