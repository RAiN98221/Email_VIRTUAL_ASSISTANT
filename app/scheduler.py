from __future__ import annotations

import asyncio
import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db
from .logging_config import get_logger


logger = get_logger(__name__)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def is_within_business_hours(now_utc: datetime, start: str, end: str, tz_name: str) -> bool:
    local = now_utc.astimezone(ZoneInfo(tz_name))
    start_time = parse_hhmm(start)
    end_time = parse_hhmm(end)
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


async def run_scheduler(stop_event: asyncio.Event, poll_seconds: int = 10) -> None:
    from .graph import mail_client

    graph = mail_client()
    while not stop_event.is_set():
        try:
            process_due_items(graph)
        except Exception:
            logger.exception("scheduler_loop_error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue


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
        if not is_within_business_hours(now, job["business_start"], job["business_end"], job["timezone"]):
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
