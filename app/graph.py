from __future__ import annotations

import smtplib
import socket
import ssl
import time
from dataclasses import asdict, dataclass
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, getaddresses, make_msgid, parsedate_to_datetime
from html import unescape
import imaplib
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
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


@dataclass(frozen=True)
class InboundReply:
    message_id: str
    from_email: str
    subject: str
    body: str
    received_at: str
    references: list[str]


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
            "deliverability": {
                "app_base_url": settings.app_base_url,
                "public_unsubscribe_links": not settings.app_base_url.startswith(("http://127.0.0.1", "http://localhost")),
            },
        }

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
            raise MailNotConfigured("Set SMTP_USERNAME, SMTP_PASSWORD, and FROM_EMAIL in .env first.")

        message_id = make_msgid(domain=(settings.from_email.split("@")[-1] or "localhost"))
        message = EmailMessage()
        message["From"] = settings.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = message_id
        if settings.from_email:
            message["Reply-To"] = settings.from_email
        for header, value in (extra_headers or {}).items():
            message[header] = value
        if content_type.lower() == "html":
            message.set_content("This message contains HTML content.")
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

    def fetch_inbound_replies(self, limit: int = 50) -> list[InboundReply]:
        if not self.is_imap_configured():
            raise MailNotConfigured("Set IMAP_USERNAME and IMAP_PASSWORD to poll Gmail replies.")
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=30) as imap:
            imap.login(settings.imap_username, settings.imap_password)
            mailbox = self._select_inbox(imap)
            if not mailbox:
                imap.logout()
                return []
            status, data = imap.search(None, "ALL")
            if status != "OK" or not data or not data[0].strip():
                imap.logout()
                return []
            ids = data[0].split()[-max(1, limit):]
            replies: list[InboundReply] = []
            for message_number in reversed(ids):
                status, fetched = imap.fetch(message_number, "(RFC822)")
                if status != "OK" or not fetched:
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple) and part[1]), None)
                if not raw:
                    continue
                reply = self._parse_inbound_message(raw)
                if reply:
                    replies.append(reply)
            imap.logout()
            return replies

    def _select_inbox(self, imap: imaplib.IMAP4_SSL) -> str | None:
        for mailbox in (b"INBOX", b'"INBOX"'):
            status, _ = imap.select(mailbox, readonly=True)
            if status == "OK":
                return mailbox.decode("utf-8", errors="replace")
        return None

    def _parse_inbound_message(self, raw: bytes) -> InboundReply | None:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        message_id = str(message.get("Message-ID") or "").strip()
        if not message_id:
            return None
        addresses = getaddresses(message.get_all("From", []))
        from_email = addresses[0][1].strip() if addresses else ""
        if not from_email:
            return None
        subject = self._decode_header_value(message.get("Subject") or "")
        received_at = self._message_received_at(message)
        references = self._reply_references(message)
        return InboundReply(
            message_id=message_id,
            from_email=from_email,
            subject=subject,
            body=self._message_body(message),
            received_at=received_at,
            references=references,
        )

    def _decode_header_value(self, value: str) -> str:
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    def _message_received_at(self, message) -> str:
        try:
            parsed = parsedate_to_datetime(str(message.get("Date") or ""))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _reply_references(self, message) -> list[str]:
        values = []
        for header in ("In-Reply-To", "References"):
            values.extend(message.get_all(header, []))
        seen: set[str] = set()
        refs = []
        for value in values:
            for match in re.findall(r"<[^>]+>", str(value)):
                if match not in seen:
                    seen.add(match)
                    refs.append(match)
        return refs

    def _message_body(self, message) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                if part.get_content_type() == "text/plain":
                    return self._part_text(part)
            for part in message.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                if part.get_content_type() == "text/html":
                    return self._html_to_text(self._part_text(part))
            return ""
        text = self._part_text(message)
        if message.get_content_type() == "text/html" or self._looks_like_html(text):
            return self._html_to_text(text)
        return text

    def _looks_like_html(self, value: str) -> bool:
        return bool(re.search(r"<!doctype|<html[\s>]|<body[\s>]|<style[\s>]", value or "", re.IGNORECASE))

    def _html_to_text(self, value: str) -> str:
        text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", value or "")
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>", "\n\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text).replace("\xa0", " ")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        compact = "\n".join(line for line in lines if line)
        return re.sub(r"\n{3,}", "\n\n", compact).strip()

    def _part_text(self, part) -> str:
        try:
            return str(part.get_content()).strip()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace").strip()

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
