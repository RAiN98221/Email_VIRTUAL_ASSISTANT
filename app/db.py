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

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                business_start TEXT NOT NULL,
                business_end TEXT NOT NULL,
                timezone TEXT NOT NULL,
                override_contacted INTEGER NOT NULL DEFAULT 0,
                content_type TEXT NOT NULL,
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
            """
        )


def contacted_emails() -> set[str]:
    with connect() as conn:
        return {row["email_norm"] for row in conn.execute("SELECT email_norm FROM contacted")}


def create_job(
    items: list[dict[str, Any]],
    interval_minutes: int,
    business_start: str,
    business_end: str,
    timezone_name: str,
    override_contacted: bool,
    content_type: str,
) -> str:
    job_id = str(uuid.uuid4())
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, interval_minutes, business_start, business_end, timezone,
                override_contacted, content_type, created_at, updated_at
            ) VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                interval_minutes,
                business_start,
                business_end,
                timezone_name,
                1 if override_contacted else 0,
                content_type,
                now,
                now,
            ),
        )
        for item in items:
            conn.execute(
                """
                INSERT INTO queue_items (
                    job_id, row_index, email, email_norm, first_name, last_name,
                    subject, body, row_data_json, status, scheduled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
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


def list_queue(job_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM queue_items"
    params: tuple[Any, ...] = ()
    if job_id:
        query += " WHERE job_id = ?"
        params = (job_id,)
    query += " ORDER BY id ASC"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def set_job_status(job_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), job_id),
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


def mark_sent(item_id: int, graph_message_id: str | None = None) -> None:
    now = utc_now()
    with connect() as conn:
        item = conn.execute("SELECT * FROM queue_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return
        conn.execute(
            """
            UPDATE queue_items
            SET status = 'sent', sent_at = ?, error = ?, attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (now, graph_message_id, now, item_id),
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
