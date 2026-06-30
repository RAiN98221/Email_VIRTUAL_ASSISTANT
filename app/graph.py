from __future__ import annotations

import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import unescape
import mimetypes
import re
from pathlib import Path
from typing import Any

from . import db
from .logging_config import get_logger
from .settings import settings


PLACEHOLDER_SMTP_VALUES = {
    "",
    "your-brevo-smtp-login",
    "your-brevo-smtp-key",
    "you@your-authenticated-domain.com",
}
logger = get_logger(__name__)


def html_to_plain_text(value: str) -> str:
    """Build a readable text/plain alternative from an HTML body.

    Anchor links are flattened to "label (url)" so recipients on text-only clients (and inbox
    preview panes) still see the destination instead of a "this message is HTML" placeholder.
    """
    text = value or ""
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", text)

    def _anchor(match: re.Match[str]) -> str:
        href = match.group(1).strip()
        label = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        label = unescape(label)
        if not href:
            return label
        return f"{label} ({href})" if label and label != href else href

    text = re.sub(r'(?is)<a\b[^>]*\bhref=["\']([^"\']*)["\'][^>]*>(.*?)</a>', _anchor, text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", compact).strip()


@dataclass(frozen=True)
class MailCredentials:
    from_email: str
    smtp_username: str
    smtp_password: str
    source: str
    provider: str = "brevo"
    from_name: str = ""
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_security: str = "starttls"


def _account_value(account: dict[str, Any], key: str, default: Any) -> Any:
    """Read a column that may be absent on very old rows before the provider migration."""
    try:
        value = account[key]
    except (KeyError, IndexError):
        return default
    return value if value not in (None, "") else default


def active_credentials() -> MailCredentials:
    """Active account added via the UI wins; otherwise fall back to .env values."""
    try:
        account = db.get_active_mail_account()
    except Exception:
        account = None
    if account:
        from_email = _account_value(account, "from_email", account["email"])
        username = _account_value(account, "smtp_username", from_email)
        return MailCredentials(
            from_email=from_email,
            smtp_username=username,
            smtp_password=account["app_password"],
            source="account",
            provider=_account_value(account, "provider", "brevo"),
            from_name=_account_value(account, "from_name", ""),
            smtp_host=_account_value(account, "smtp_host", "smtp-relay.brevo.com"),
            smtp_port=int(_account_value(account, "smtp_port", 587)),
            smtp_security=_account_value(account, "smtp_security", "starttls"),
        )
    return MailCredentials(
        from_email=settings.from_email,
        smtp_username=settings.smtp_username,
        smtp_password=settings.smtp_password,
        source="env",
        provider=settings.mail_provider,
        from_name=settings.from_name,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_security=settings.smtp_security,
    )


class MailNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class SendResult:
    smtp_accepted: bool
    message_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "smtp_accepted": self.smtp_accepted,
            "message_id": self.message_id,
            "meaning": "SMTP accepted the message; recipient inbox delivery is not confirmed.",
        }


class SmtpConnectMixin:
    def _get_socket(self, host: str, port: int, timeout: float):
        connect_host = settings.smtp_connect_host.strip() or host
        return socket.create_connection((connect_host, port), timeout)


class SmtpPlain(SmtpConnectMixin, smtplib.SMTP):
    pass


class SmtpSsl(SmtpConnectMixin, smtplib.SMTP_SSL):
    def _get_socket(self, host: str, port: int, timeout: float):
        raw_socket = SmtpConnectMixin._get_socket(self, host, port, timeout)
        context = self.context or ssl.create_default_context()
        return context.wrap_socket(raw_socket, server_hostname=host)


def _uses_ssl(security: str, port: int) -> bool:
    return security.strip().lower() == "ssl" or int(port) == 465


def _open_smtp(host: str, port: int, security: str, timeout: float):
    """Open an SMTP session, returning a context manager already past EHLO/STARTTLS."""
    if _uses_ssl(security, port):
        smtp = SmtpSsl(host, port, timeout=timeout)
        smtp.ehlo()
        return smtp
    smtp = SmtpPlain(host, port, timeout=timeout)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    return smtp


class MailClient:
    def is_configured(self) -> bool:
        credentials = active_credentials()
        return (
            credentials.smtp_host.strip() not in PLACEHOLDER_SMTP_VALUES
            and credentials.smtp_username.strip() not in PLACEHOLDER_SMTP_VALUES
            and credentials.smtp_password.strip() not in PLACEHOLDER_SMTP_VALUES
            and credentials.from_email.strip() not in PLACEHOLDER_SMTP_VALUES
        )

    def auth_status(self) -> dict[str, Any]:
        credentials = active_credentials()
        return {
            "provider": credentials.provider,
            "configured": self.is_configured(),
            "authenticated": self.is_configured(),
            "account": credentials.from_email or credentials.smtp_username or None,
            "account_source": credentials.source,
            "smtp_host": credentials.smtp_host,
            "connect_host": settings.smtp_connect_host or credentials.smtp_host,
        }

    def verify_login(
        self,
        username: str,
        password: str,
        *,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_security: str | None = None,
    ) -> None:
        """Raises on connection or authentication failure."""
        host = smtp_host or settings.smtp_host
        port = int(smtp_port if smtp_port is not None else settings.smtp_port)
        security = smtp_security or settings.smtp_security
        with _open_smtp(host, port, security, timeout=20) as smtp:
            smtp.login(username, password)

    def send_mail(
        self,
        to_email: str,
        subject: str,
        body: str,
        content_type: str = "Text",
        extra_headers: dict[str, str] | None = None,
        attachments: list[Path] | None = None,
    ) -> SendResult:
        if not self.is_configured():
            raise MailNotConfigured("Add an email provider in Settings or set SMTP_USERNAME, SMTP_PASSWORD, and FROM_EMAIL in .env first.")

        credentials = active_credentials()
        message_id = make_msgid(domain=(credentials.from_email.split("@")[-1] or "localhost"))
        message = EmailMessage()
        message["From"] = (
            formataddr((credentials.from_name, credentials.from_email))
            if credentials.from_name
            else credentials.from_email
        )
        message["To"] = to_email
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = message_id
        if credentials.from_email:
            message["Reply-To"] = (
                formataddr((credentials.from_name, credentials.from_email))
                if credentials.from_name
                else credentials.from_email
            )
        for header, value in (extra_headers or {}).items():
            message[header] = value
        if content_type.lower() == "html":
            plain_alternative = html_to_plain_text(body) or "This message contains HTML content."
            message.set_content(plain_alternative)
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)
        for attachment in attachments or []:
            content_type_guess, _ = mimetypes.guess_type(attachment.name)
            maintype, subtype = (content_type_guess or "application/octet-stream").split("/", 1)
            message.add_attachment(
                attachment.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment.name,
            )

        host = credentials.smtp_host
        port = credentials.smtp_port
        security = credentials.smtp_security
        logger.info(
            "smtp_send_start provider=%s host=%s connect_host=%s port=%s from=%s to=%s content_type=%s",
            credentials.provider,
            host,
            settings.smtp_connect_host or host,
            port,
            credentials.from_email,
            to_email,
            content_type,
        )
        try:
            with _open_smtp(host, port, security, timeout=60) as smtp:
                logger.info("smtp_connected host=%s port=%s to=%s", host, port, to_email)
                smtp.login(credentials.smtp_username, credentials.smtp_password)
                logger.info("smtp_login_ok username=%s to=%s", credentials.smtp_username, to_email)
                smtp.send_message(message)
            logger.info("smtp_send_ok to=%s subject=%r", to_email, subject)
        except Exception:
            logger.exception("smtp_send_failed host=%s port=%s to=%s", host, port, to_email)
            raise

        return SendResult(smtp_accepted=True, message_id=message_id)


def mail_client() -> MailClient:
    return MailClient()
