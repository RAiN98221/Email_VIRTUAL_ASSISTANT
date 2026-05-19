from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .contacts import (
    load_contacts,
    normalize_email,
    render_template,
    validate_contact,
)
from .graph import mail_client
from .scheduler import run_scheduler
from .settings import ROOT_DIR, settings


class PreviewRequest(BaseModel):
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    csv_file: str | None = None
    content_type: Literal["Text", "HTML"] = "Text"
    override_contacted: bool = False


class QueueRequest(PreviewRequest):
    selected_row_indexes: list[int] | None = None
    send_limit: int | None = Field(default=None, ge=1, le=10000)
    interval_minutes: int = Field(default=10, ge=1, le=1440)
    business_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    business_end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "America/Chicago"


app = FastAPI(title="CSV Email Assistant")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
_stop_event: asyncio.Event | None = None
_scheduler_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup() -> None:
    global _stop_event, _scheduler_task
    db.init_db()
    _stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(run_scheduler(_stop_event))


@app.on_event("shutdown")
async def shutdown() -> None:
    if _stop_event:
        _stop_event.set()
    if _scheduler_task:
        await _scheduler_task


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "static" / "index.html")


@app.get("/api/auth/status")
def auth_status() -> dict:
    return mail_client().auth_status()


def available_csv_files() -> list[dict[str, str | bool]]:
    default_name = settings.default_csv_path.name
    return [
        {
            "name": path.name,
            "path": str(path),
            "default": path.name == default_name,
        }
        for path in sorted(ROOT_DIR.glob("*.csv"))
    ]


def selected_csv_path(csv_file: str | None = None):
    csv_files = {item["name"]: item["path"] for item in available_csv_files()}
    if not csv_file:
        return settings.default_csv_path
    if csv_file not in csv_files:
        raise HTTPException(status_code=400, detail="Unknown CSV file.")
    return ROOT_DIR / csv_file


@app.get("/api/csv-files")
def csv_files() -> dict:
    return {"files": available_csv_files()}


@app.get("/api/contacts")
def contacts(csv_file: str | None = None) -> dict:
    csv_path = selected_csv_path(csv_file)
    loaded = load_contacts(csv_path)
    return {
        "csv_file": csv_path.name,
        "csv_path": str(csv_path),
        "count": len(loaded),
        "columns": [
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "state",
            "birth_date",
            "age",
            "gender",
        ],
    }


def build_preview(payload: PreviewRequest) -> dict:
    contacts = load_contacts(selected_csv_path(payload.csv_file))
    contacted = db.contacted_emails()
    seen: set[str] = set()
    rows = []
    summary = {
        "total": len(contacts),
        "sendable": 0,
        "invalid": 0,
        "already_contacted": 0,
        "duplicates": 0,
    }
    for contact in contacts:
        errors = validate_contact(contact)
        subject, missing_subject = render_template(payload.subject, contact.row_data)
        body, missing_body = render_template(payload.body, contact.row_data)
        email_norm = normalize_email(contact.email)
        already_contacted = email_norm in contacted
        duplicate_in_csv = email_norm in seen
        if email_norm:
            seen.add(email_norm)
        missing = sorted(set(missing_subject + missing_body))
        if missing:
            errors.append("missing_template_value")
        if duplicate_in_csv:
            errors.append("duplicate_in_csv")
            summary["duplicates"] += 1
        if already_contacted and not payload.override_contacted:
            errors.append("already_contacted")
            summary["already_contacted"] += 1
        sendable = not errors
        summary["sendable" if sendable else "invalid"] += 1
        rows.append(
            {
                "row_index": contact.row_index,
                "email": contact.email,
                "email_norm": email_norm,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "subject": subject,
                "body": body,
                "missing_variables": missing,
                "already_contacted": already_contacted,
                "duplicate_in_csv": duplicate_in_csv,
                "errors": errors,
                "sendable": sendable,
                "row_data": contact.row_data,
            }
        )
    return {"summary": summary, "rows": rows}


@app.post("/api/preview")
def preview(payload: PreviewRequest) -> dict:
    return build_preview(payload)


@app.post("/api/jobs")
def create_job(payload: QueueRequest) -> dict:
    preview_data = build_preview(payload)
    items = [row for row in preview_data["rows"] if row["sendable"]]
    if payload.selected_row_indexes is not None:
        selected = set(payload.selected_row_indexes)
        items = [row for row in items if row["row_index"] in selected]
    if payload.send_limit is not None:
        items = items[: payload.send_limit]
    if not items:
        raise HTTPException(status_code=400, detail="No sendable contacts after validation.")
    job_id = db.create_job(
        items=items,
        interval_minutes=payload.interval_minutes,
        business_start=payload.business_start,
        business_end=payload.business_end,
        timezone_name=payload.timezone,
        override_contacted=payload.override_contacted,
        content_type=payload.content_type,
    )
    return {"job_id": job_id, "queued": len(items), "summary": preview_data["summary"]}


@app.get("/api/jobs")
def jobs() -> dict:
    return {"jobs": db.list_jobs()}


@app.get("/api/jobs/{job_id}/queue")
def queue(job_id: str) -> dict:
    return {"items": db.list_queue(job_id)}


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict:
    db.set_job_status(job_id, "paused")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    db.set_job_status(job_id, "running")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    db.set_job_status(job_id, "cancelled")
    return {"ok": True}


@app.get("/api/history")
def history() -> dict:
    return {"contacts": db.contacted_history()}
