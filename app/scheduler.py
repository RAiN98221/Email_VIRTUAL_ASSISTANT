from __future__ import annotations

import asyncio
import json
import random
import smtplib
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db
from .logging_config import get_logger
from .settings import ROOT_DIR, settings


logger = get_logger(__name__)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


class ScheduleConfigError(ValueError):
    """Raised when a job has an unusable timezone or business-hour window."""


def is_within_business_hours(now_utc: datetime, start: str, end: str, tz_name: str) -> bool:
    try:
        local = now_utc.astimezone(ZoneInfo(tz_name))
        start_time = parse_hhmm(start)
        end_time = parse_hhmm(end)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ScheduleConfigError(str(exc)) from exc
    if start_time <= end_time:
        return start_time <= local.time() <= end_time
    return local.time() >= start_time or local.time() <= end_time


def local_day_window_utc(now_utc: datetime, tz_name: str) -> tuple[datetime, datetime]:
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def sent_today_count(job_id: str, now_utc: datetime, tz_name: str) -> int:
    start_utc, end_utc = local_day_window_utc(now_utc, tz_name)
    return db.count_sent_between(job_id, start_utc.isoformat(), end_utc.isoformat())


def next_scheduled_at(after_utc: datetime, interval_minutes: int, jitter_minutes: int = 0) -> str:
    jitter = random.randint(-jitter_minutes, jitter_minutes) if jitter_minutes > 0 else 0
    delay_minutes = max(1, interval_minutes + jitter)
    return (after_utc + timedelta(minutes=delay_minutes)).isoformat()


def job_attachment_paths(job) -> list[Path]:
    try:
        files = json.loads(job["attachment_files"] or "[]")
    except (TypeError, json.JSONDecodeError):
        files = []
    paths = []
    for file_id in files:
        path = (ROOT_DIR / file_id).resolve()
        try:
            path.relative_to(ROOT_DIR)
        except ValueError:
            logger.warning("attachment_path_outside_root job_id=%s path=%s", job["id"], path)
            continue
        if path.is_file():
            paths.append(path)
        else:
            logger.warning("attachment_missing job_id=%s path=%s", job["id"], path)
    return paths


def smtp_failure_suppression_reason(exc: Exception) -> str | None:
    codes: list[int] = []
    detail_parts: list[str] = []
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        for code, detail in exc.recipients.values():
            codes.append(int(code))
            detail_parts.append(str(detail))
    elif isinstance(exc, smtplib.SMTPResponseException):
        codes.append(int(exc.smtp_code))
        detail_parts.append(str(exc.smtp_error))

    detail = " ".join(detail_parts + [str(exc)]).lower()
    if codes and not all(500 <= code <= 599 for code in codes):
        return None
    if not codes and not any(term in detail for term in ("550", "551", "553", "554", "5.1.", "5.2.")):
        return None
    if any(term in detail for term in ("blocked", "policy", "spam", "prohibited", "denied")):
        return "blocked"
    if any(term in detail for term in ("user unknown", "no such", "mailbox", "invalid", "recipient")):
        return "bounced"
    return "bounced" if codes else None


async def run_scheduler(stop_event: asyncio.Event, poll_seconds: int = 10) -> None:
    from .graph import mail_client

    graph = mail_client()
    last_reply_poll: datetime | None = datetime.now(timezone.utc)
    while not stop_event.is_set():
        try:
            process_due_items(graph)
            now = datetime.now(timezone.utc)
            if (
                settings.reply_poll_enabled
                and (last_reply_poll is None or (now - last_reply_poll).total_seconds() >= settings.reply_poll_seconds)
            ):
                sync_inbound_replies(graph)
                last_reply_poll = now
        except Exception:
            logger.exception("scheduler_loop_error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue


def sync_inbound_replies(graph) -> int:
    try:
        replies = graph.fetch_inbound_replies(limit=settings.reply_poll_limit)
    except Exception as exc:
        logger.warning("reply_poll_failed detail=%s", exc)
        return 0
    saved = 0
    from .contacts import normalize_email

    for reply in replies:
        from_email_norm = normalize_email(reply.from_email)
        if not db.queue_item_for_reply(reply.references, from_email_norm):
            continue
        if db.record_inbound_reply(
            message_id=reply.message_id,
            from_email=reply.from_email,
            from_email_norm=from_email_norm,
            subject=reply.subject,
            body=reply.body,
            received_at=reply.received_at,
            references=reply.references,
        ):
            saved += 1
    if saved:
        logger.info("reply_poll_synced count=%s", saved)
    return saved


def process_due_items(graph) -> None:
    now = datetime.now(timezone.utc)
    with db.connect() as conn:
        job = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'running'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if not job:
            return
        try:
            within_hours = is_within_business_hours(
                now, job["business_start"], job["business_end"], job["timezone"]
            )
        except ScheduleConfigError as exc:
            # A single misconfigured job must not stall every other running campaign, so pause it.
            db.set_job_status(
                job["id"],
                "paused",
                f"Auto-paused: invalid schedule configuration ({exc}). Fix the timezone or send window.",
            )
            logger.warning(
                "queue_schedule_config_invalid job_id=%s timezone=%s start=%s end=%s detail=%s",
                job["id"],
                job["timezone"],
                job["business_start"],
                job["business_end"],
                exc,
            )
            return
        if not within_hours:
            return
        sent_today = sent_today_count(job["id"], now, job["timezone"])
        if sent_today >= int(job["daily_send_limit"]):
            logger.info(
                "queue_daily_cap_reached job_id=%s sent_today=%s daily_limit=%s",
                job["id"],
                sent_today,
                job["daily_send_limit"],
            )
            return
        item = conn.execute(
            """
            SELECT * FROM queue_items
            WHERE job_id = ? AND status = 'pending'
              AND (scheduled_at IS NULL OR scheduled_at <= ?)
            ORDER BY id ASC
            LIMIT 1
            """,
            (job["id"], now.isoformat()),
        ).fetchone()
        if not item:
            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM queue_items WHERE job_id = ? AND status = 'pending'",
                (job["id"],),
            ).fetchone()["count"]
            if remaining == 0:
                conn.execute(
                    "UPDATE jobs SET status = 'completed', updated_at = ? WHERE id = ?",
                    (db.utc_now(), job["id"]),
                )
            return
        conn.execute(
            "UPDATE queue_items SET status = 'sending', updated_at = ? WHERE id = ?",
            (db.utc_now(), item["id"]),
        )

    try:
        logger.info("queue_send_start job_id=%s item_id=%s to=%s", job["id"], item["id"], item["email"])
        send_result = graph.send_mail(
            to_email=item["email"],
            subject=item["subject"],
            body=item["body"],
            content_type=job["content_type"],
            attachments=job_attachment_paths(job),
        )
        db.mark_sent(
            item["id"],
            smtp_message_id=send_result.message_id,
            verification_status=send_result.verification.status,
            verification_detail=send_result.verification.detail,
        )
        logger.info(
            "queue_send_ok job_id=%s item_id=%s to=%s verification=%s",
            job["id"],
            item["id"],
            item["email"],
            send_result.verification.status,
        )
    except Exception as exc:
        db.mark_failed(item["id"], str(exc))
        suppression_reason = smtp_failure_suppression_reason(exc)
        if suppression_reason:
            db.suppress_email(
                item["email"],
                item["email_norm"],
                suppression_reason,
                "smtp_failure",
                str(exc)[:500],
            )
            logger.warning(
                "queue_recipient_suppressed job_id=%s item_id=%s to=%s reason=%s",
                job["id"],
                item["id"],
                item["email"],
                suppression_reason,
            )
        failed_count = db.count_failed(job["id"])
        if int(job["auto_pause_on_failure"]) and failed_count >= int(job["max_failures"]):
            pause_reason = f"Auto-paused after {failed_count} failed send attempt(s)."
            db.set_job_status(job["id"], "paused", pause_reason)
            logger.warning(
                "queue_auto_paused job_id=%s failed_count=%s max_failures=%s",
                job["id"],
                failed_count,
                job["max_failures"],
            )
        logger.exception("queue_send_failed job_id=%s item_id=%s to=%s", job["id"], item["id"], item["email"])

    scheduled_at = next_scheduled_at(
        datetime.now(timezone.utc),
        int(job["interval_minutes"]),
        int(job["interval_jitter_minutes"]),
    )
    with db.connect() as conn:
        conn.execute(
            """
            UPDATE queue_items
            SET scheduled_at = ?, updated_at = ?
            WHERE job_id = ? AND status = 'pending'
            """,
            (scheduled_at, db.utc_now(), job["id"]),
        )
