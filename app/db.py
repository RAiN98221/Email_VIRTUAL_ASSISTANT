from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .settings import settings

_database_path: Path = settings.database_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_database(path: Path) -> None:
    global _database_path
    _database_path = path


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = path or _database_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contacted (
                email_norm TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                first_contacted_at TEXT NOT NULL,
                last_contacted_at TEXT NOT NULL,
                job_id TEXT NOT NULL,
                row_data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS suppressed_contacts (
                email_norm TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                campaign_name TEXT,
                status TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                interval_jitter_minutes INTEGER NOT NULL DEFAULT 0,
                daily_send_limit INTEGER NOT NULL DEFAULT 25,
                max_failures INTEGER NOT NULL DEFAULT 3,
                auto_pause_on_failure INTEGER NOT NULL DEFAULT 1,
                pause_reason TEXT,
                business_start TEXT NOT NULL,
                business_end TEXT NOT NULL,
                timezone TEXT NOT NULL,
                override_contacted INTEGER NOT NULL DEFAULT 0,
                content_type TEXT NOT NULL,
                attachment_files TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                row_index INTEGER NOT NULL,
                email TEXT NOT NULL,
                email_norm TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                row_data_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                scheduled_at TEXT,
                sent_at TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_queue_status_schedule
                ON queue_items(status, scheduled_at);
            CREATE INDEX IF NOT EXISTS idx_queue_email_norm
                ON queue_items(email_norm);

            CREATE TABLE IF NOT EXISTS inbound_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                from_email TEXT NOT NULL,
                from_email_norm TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                received_at TEXT NOT NULL,
                matched_queue_item_id INTEGER REFERENCES queue_items(id) ON DELETE SET NULL,
                job_id TEXT,
                campaign_name TEXT,
                response_body TEXT,
                responded_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_inbound_replies_received_at
                ON inbound_replies(received_at);
            CREATE INDEX IF NOT EXISTS idx_inbound_replies_from_email_norm
                ON inbound_replies(from_email_norm);

            CREATE TABLE IF NOT EXISTS email_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gmail_accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                app_password TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        existing_queue_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(queue_items)").fetchall()
        }
        queue_migrations = {
            "smtp_message_id": "ALTER TABLE queue_items ADD COLUMN smtp_message_id TEXT",
            "verification_status": "ALTER TABLE queue_items ADD COLUMN verification_status TEXT",
            "verification_detail": "ALTER TABLE queue_items ADD COLUMN verification_detail TEXT",
            "verified_at": "ALTER TABLE queue_items ADD COLUMN verified_at TEXT",
            "template_name": "ALTER TABLE queue_items ADD COLUMN template_name TEXT",
        }
        for column, statement in queue_migrations.items():
            if column not in existing_queue_columns:
                conn.execute(statement)

        existing_job_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        job_migrations = {
            "campaign_name": "ALTER TABLE jobs ADD COLUMN campaign_name TEXT",
            "interval_jitter_minutes": (
                "ALTER TABLE jobs ADD COLUMN interval_jitter_minutes INTEGER NOT NULL DEFAULT 0"
            ),
            "daily_send_limit": "ALTER TABLE jobs ADD COLUMN daily_send_limit INTEGER NOT NULL DEFAULT 25",
            "max_failures": "ALTER TABLE jobs ADD COLUMN max_failures INTEGER NOT NULL DEFAULT 3",
            "auto_pause_on_failure": (
                "ALTER TABLE jobs ADD COLUMN auto_pause_on_failure INTEGER NOT NULL DEFAULT 1"
            ),
            "pause_reason": "ALTER TABLE jobs ADD COLUMN pause_reason TEXT",
            "attachment_files": "ALTER TABLE jobs ADD COLUMN attachment_files TEXT",
            "template_rotation": "ALTER TABLE jobs ADD COLUMN template_rotation TEXT",
        }
        for column, statement in job_migrations.items():
            if column not in existing_job_columns:
                conn.execute(statement)

        existing_reply_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(inbound_replies)").fetchall()
        }
        reply_migrations = {
            "response_body": "ALTER TABLE inbound_replies ADD COLUMN response_body TEXT",
            "responded_at": "ALTER TABLE inbound_replies ADD COLUMN responded_at TEXT",
        }
        for column, statement in reply_migrations.items():
            if column not in existing_reply_columns:
                conn.execute(statement)


def list_gmail_accounts() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM gmail_accounts ORDER BY created_at")
        ]


def get_active_gmail_account() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM gmail_accounts WHERE is_active = 1").fetchone()
        return dict(row) if row else None


def add_gmail_account(email: str, app_password: str, activate: bool = False) -> dict[str, Any]:
    now = utc_now()
    account_id = str(uuid.uuid4())
    with connect() as conn:
        if activate:
            conn.execute("UPDATE gmail_accounts SET is_active = 0, updated_at = ? WHERE is_active = 1", (now,))
        conn.execute(
            """
            INSERT INTO gmail_accounts (id, email, app_password, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account_id, email.strip().lower(), app_password, 1 if activate else 0, now, now),
        )
        row = conn.execute("SELECT * FROM gmail_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row)


def set_active_gmail_account(account_id: str) -> dict[str, Any] | None:
    now = utc_now()
    with connect() as conn:
        row = conn.execute("SELECT * FROM gmail_accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE gmail_accounts SET is_active = 0, updated_at = ? WHERE is_active = 1", (now,))
        conn.execute("UPDATE gmail_accounts SET is_active = 1, updated_at = ? WHERE id = ?", (now, account_id))
        return dict(conn.execute("SELECT * FROM gmail_accounts WHERE id = ?", (account_id,)).fetchone())


def deactivate_gmail_accounts() -> None:
    with connect() as conn:
        conn.execute("UPDATE gmail_accounts SET is_active = 0, updated_at = ? WHERE is_active = 1", (utc_now(),))


def delete_gmail_account(account_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM gmail_accounts WHERE id = ?", (account_id,))
        return cursor.rowcount > 0


def contacted_emails() -> set[str]:
    with connect() as conn:
        return {row["email_norm"] for row in conn.execute("SELECT email_norm FROM contacted")}


def list_templates() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM email_templates ORDER BY updated_at DESC")
        ]


def get_template(template_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM email_templates WHERE id = ?", (template_id,)).fetchone()
        return dict(row) if row else None


def save_template(
    name: str,
    subject: str,
    body: str,
    template_id: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    template_id = template_id or str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO email_templates (id, name, subject, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                subject = excluded.subject,
                body = excluded.body,
                updated_at = excluded.updated_at
            """,
            (template_id, name.strip() or "Untitled Template", subject, body, now, now),
        )
        row = conn.execute("SELECT * FROM email_templates WHERE id = ?", (template_id,)).fetchone()
        return dict(row)


def delete_template(template_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM email_templates WHERE id = ?", (template_id,))
        return cursor.rowcount > 0


def suppressed_emails() -> dict[str, dict[str, Any]]:
    with connect() as conn:
        return {
            row["email_norm"]: dict(row)
            for row in conn.execute("SELECT * FROM suppressed_contacts ORDER BY updated_at DESC")
        }


def suppression_history() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM suppressed_contacts ORDER BY updated_at DESC")
        ]


def suppress_email(
    email: str,
    email_norm: str,
    reason: str,
    source: str,
    note: str | None = None,
) -> None:
    if not email_norm:
        return
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO suppressed_contacts (
                email_norm, email, reason, source, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email_norm) DO UPDATE SET
                email = excluded.email,
                reason = excluded.reason,
                source = excluded.source,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (email_norm, email, reason, source, note, now, now),
        )


def unsuppress_email(email_norm: str) -> bool:
    if not email_norm:
        return False
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM suppressed_contacts WHERE email_norm = ?",
            (email_norm,),
        )
        return cursor.rowcount > 0


def create_job(
    campaign_name: str,
    items: list[dict[str, Any]],
    interval_minutes: int,
    interval_jitter_minutes: int,
    daily_send_limit: int,
    max_failures: int,
    auto_pause_on_failure: bool,
    business_start: str,
    business_end: str,
    timezone_name: str,
    override_contacted: bool,
    content_type: str,
    attachment_files: list[str] | None = None,
    template_rotation: list[str] | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, campaign_name, status, interval_minutes, interval_jitter_minutes, daily_send_limit,
                max_failures, auto_pause_on_failure, business_start, business_end, timezone,
                override_contacted, content_type, attachment_files, template_rotation, created_at, updated_at
            ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                campaign_name,
                interval_minutes,
                interval_jitter_minutes,
                daily_send_limit,
                max_failures,
                1 if auto_pause_on_failure else 0,
                business_start,
                business_end,
                timezone_name,
                1 if override_contacted else 0,
                content_type,
                json.dumps(attachment_files or [], ensure_ascii=True),
                json.dumps(template_rotation or [], ensure_ascii=True),
                now,
                now,
            ),
        )
        for item in items:
            conn.execute(
                """
                INSERT INTO queue_items (
                    job_id, row_index, email, email_norm, first_name, last_name,
                    subject, body, template_name, row_data_json, status, scheduled_at, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    job_id,
                    item["row_index"],
                    item["email"],
                    item["email_norm"],
                    item.get("first_name", ""),
                    item.get("last_name", ""),
                    item["subject"],
                    item["body"],
                    item.get("template_name"),
                    json.dumps(item["row_data"], ensure_ascii=True),
                    now,
                    now,
                    now,
                ),
            )
    return job_id


def list_jobs() -> list[dict[str, Any]]:
    with connect() as conn:
        jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
        for job in jobs:
            counts = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM queue_items
                WHERE job_id = ?
                GROUP BY status
                """,
                (job["id"],),
            ).fetchall()
            job["counts"] = {row["status"]: row["count"] for row in counts}
        return jobs


def email_status_summary() -> dict[str, Any]:
    statuses = {
        "queued": 0,
        "sending": 0,
        "sent": 0,
        "received": 0,
        "replied": 0,
        "failed": 0,
        "cancelled": 0,
    }
    status_map = {
        "pending": "queued",
        "sending": "sending",
        "sent": "sent",
        "failed": "failed",
        "cancelled": "cancelled",
    }
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM queue_items
            GROUP BY status
            """
        ).fetchall()
        for row in rows:
            key = status_map.get(row["status"], row["status"])
            statuses[key] = statuses.get(key, 0) + row["count"]
        reply_counts = conn.execute(
            """
            SELECT
                COUNT(*) AS received_count,
                COUNT(matched_queue_item_id) AS replied_count
            FROM inbound_replies
            """
        ).fetchone()
        statuses["received"] = reply_counts["received_count"] or 0
        statuses["replied"] = reply_counts["replied_count"] or 0
    total = sum(statuses.values())
    return {
        "total": total,
        "statuses": [
            {"key": key, "label": label, "count": statuses[key]}
            for key, label in (
                ("queued", "Queued"),
                ("sending", "Sending"),
                ("sent", "Sent"),
                ("received", "Received"),
                ("replied", "Replied"),
                ("failed", "Failed"),
                ("cancelled", "Cancelled"),
            )
        ],
    }


def count_sent_between(job_id: str, start_utc: str, end_utc: str) -> int:
    with connect() as conn:
        return conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM queue_items
            WHERE job_id = ? AND status = 'sent' AND sent_at >= ? AND sent_at < ?
            """,
            (job_id, start_utc, end_utc),
        ).fetchone()["count"]


def count_failed(job_id: str) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS count FROM queue_items WHERE job_id = ? AND status = 'failed'",
            (job_id,),
        ).fetchone()["count"]


def list_queue(job_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM queue_items"
    params: tuple[Any, ...] = ()
    if job_id:
        query += " WHERE job_id = ?"
        params = (job_id,)
    query += " ORDER BY id ASC"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def delete_job(job_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0


def set_job_status(job_id: str, status: str, pause_reason: str | None = None) -> None:
    reason = pause_reason if status == "paused" else None
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, pause_reason = ?, updated_at = ? WHERE id = ?",
            (status, reason, utc_now(), job_id),
        )
        if status == "cancelled":
            conn.execute(
                """
                UPDATE queue_items
                SET status = 'cancelled', updated_at = ?
                WHERE job_id = ? AND status = 'pending'
                """,
                (utc_now(), job_id),
            )


def mark_sent(
    item_id: int,
    smtp_message_id: str | None = None,
    verification_status: str | None = None,
    verification_detail: str | None = None,
) -> None:
    now = utc_now()
    with connect() as conn:
        item = conn.execute("SELECT * FROM queue_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return
        conn.execute(
            """
            UPDATE queue_items
            SET status = 'sent', sent_at = ?, error = NULL, smtp_message_id = ?,
                verification_status = ?, verification_detail = ?, verified_at = ?,
                attempt_count = attempt_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (
                now,
                smtp_message_id,
                verification_status,
                verification_detail,
                now if verification_status else None,
                now,
                item_id,
            ),
        )
        existing = conn.execute(
            "SELECT email_norm FROM contacted WHERE email_norm = ?", (item["email_norm"],)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE contacted
                SET last_contacted_at = ?, job_id = ?, row_data_json = ?
                WHERE email_norm = ?
                """,
                (now, item["job_id"], item["row_data_json"], item["email_norm"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO contacted (
                    email_norm, email, first_name, last_name, first_contacted_at,
                    last_contacted_at, job_id, row_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["email_norm"],
                    item["email"],
                    item["first_name"],
                    item["last_name"],
                    now,
                    now,
                    item["job_id"],
                    item["row_data_json"],
                ),
            )


def queue_item_for_reply(
    references: list[str] | None = None,
    from_email_norm: str | None = None,
) -> dict[str, Any] | None:
    refs = [ref for ref in (references or []) if ref]
    with connect() as conn:
        for ref in refs:
            item = conn.execute(
                """
                SELECT queue_items.*, jobs.campaign_name
                FROM queue_items
                JOIN jobs ON jobs.id = queue_items.job_id
                WHERE queue_items.smtp_message_id = ?
                ORDER BY queue_items.sent_at DESC
                LIMIT 1
                """,
                (ref,),
            ).fetchone()
            if item:
                return dict(item)
        if from_email_norm:
            item = conn.execute(
                """
                SELECT queue_items.*, jobs.campaign_name
                FROM queue_items
                JOIN jobs ON jobs.id = queue_items.job_id
                WHERE queue_items.email_norm = ?
                  AND queue_items.status IN ('sent', 'replied')
                ORDER BY queue_items.sent_at DESC, queue_items.updated_at DESC
                LIMIT 1
                """,
                (from_email_norm,),
            ).fetchone()
            if item:
                return dict(item)
    return None


def record_inbound_reply(
    message_id: str,
    from_email: str,
    from_email_norm: str,
    subject: str,
    body: str,
    received_at: str,
    references: list[str] | None = None,
) -> dict[str, Any] | None:
    if not message_id:
        return None
    now = utc_now()
    matched = queue_item_for_reply(references, from_email_norm)
    matched_id = matched["id"] if matched else None
    job_id = matched["job_id"] if matched else None
    campaign_name = matched.get("campaign_name") if matched else None
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO inbound_replies (
                message_id, from_email, from_email_norm, subject, body, received_at,
                matched_queue_item_id, job_id, campaign_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                from_email = excluded.from_email,
                from_email_norm = excluded.from_email_norm,
                subject = excluded.subject,
                body = excluded.body,
                received_at = excluded.received_at,
                matched_queue_item_id = COALESCE(inbound_replies.matched_queue_item_id, excluded.matched_queue_item_id),
                job_id = COALESCE(inbound_replies.job_id, excluded.job_id),
                campaign_name = COALESCE(inbound_replies.campaign_name, excluded.campaign_name),
                updated_at = excluded.updated_at
            """,
            (
                message_id,
                from_email,
                from_email_norm,
                subject,
                body,
                received_at,
                matched_id,
                job_id,
                campaign_name,
                now,
                now,
            ),
        )
        if matched_id:
            conn.execute(
                """
                UPDATE queue_items
                SET status = 'replied', updated_at = ?
                WHERE id = ? AND status IN ('sent', 'replied')
                """,
                (now, matched_id),
            )
        row = conn.execute(
            "SELECT * FROM inbound_replies WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return dict(row) if row else None


def list_replies() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT inbound_replies.*, queue_items.email AS recipient_email
                FROM inbound_replies
                LEFT JOIN queue_items ON queue_items.id = inbound_replies.matched_queue_item_id
                ORDER BY inbound_replies.received_at DESC, inbound_replies.id DESC
                """
            )
        ]


def get_reply(reply_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM inbound_replies WHERE id = ?", (reply_id,)).fetchone()
        return dict(row) if row else None


def mark_reply_responded(reply_id: int, response_body: str) -> dict[str, Any] | None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            UPDATE inbound_replies
            SET response_body = ?, responded_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (response_body, now, now, reply_id),
        )
        row = conn.execute("SELECT * FROM inbound_replies WHERE id = ?", (reply_id,)).fetchone()
        return dict(row) if row else None


def mark_failed(item_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE queue_items
            SET status = 'failed', error = ?, attempt_count = attempt_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (error[:1000], utc_now(), item_id),
        )


def contacted_history() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM contacted ORDER BY last_contacted_at DESC")
        ]
