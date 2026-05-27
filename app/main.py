from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .contacts import (
    load_contacts,
    normalize_email,
    render_template,
    is_valid_email,
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
    interval_jitter_minutes: int = Field(default=2, ge=0, le=1440)
    daily_send_limit: int = Field(default=25, ge=1, le=10000)
    business_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    business_end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "America/Chicago"


class SendTestRequest(BaseModel):
    to_email: str = Field(min_length=3)
    subject: str = "CSV Email Assistant live verification"
    body: str = "This is a controlled live-send verification from the local CSV Email Assistant."
    content_type: Literal["Text", "HTML"] = "Text"


app = FastAPI(title="CSV Email Assistant")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
_stop_event: asyncio.Event | None = None
_scheduler_task: asyncio.Task | None = None
CSV_UPLOAD_DIR = ROOT_DIR / "uploaded_csv"
MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024


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


@app.post("/api/send-test")
def send_test(payload: SendTestRequest) -> dict:
    if not is_valid_email(payload.to_email):
        raise HTTPException(status_code=400, detail="Enter a valid test recipient email address.")
    try:
        result = mail_client().send_mail(
            to_email=payload.to_email,
            subject=payload.subject,
            body=payload.body,
            content_type=payload.content_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Live send failed: {exc}") from exc
    return {
        "ok": True,
        "recipient": payload.to_email,
        "result": result.as_dict(),
        "delivery_confirmed": False,
        "delivery_note": (
            "This verifies SMTP acceptance and, when enabled, Gmail Sent Mail visibility. "
            "It does not prove the recipient inbox accepted or displayed the email."
        ),
    }


def csv_file_id(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def available_csv_files() -> list[dict[str, str | bool]]:
    default_name = settings.default_csv_path.name
    paths = [*sorted(ROOT_DIR.glob("*.csv"))]
    if CSV_UPLOAD_DIR.exists():
        paths.extend(sorted(CSV_UPLOAD_DIR.glob("*.csv")))
    return [
        {
            "name": csv_file_id(path),
            "display_name": path.name,
            "path": str(path),
            "default": path.name == default_name and path.parent == ROOT_DIR,
            "uploaded": path.parent == CSV_UPLOAD_DIR,
        }
        for path in paths
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


def safe_upload_name(filename: str) -> str:
    base = Path(filename or "contacts.csv").name
    stem = Path(base).stem or "contacts"
    suffix = Path(base).suffix.lower()
    if suffix != ".csv":
        raise HTTPException(status_code=400, detail="Choose a .csv contact file.")
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "contacts"
    return f"{safe_stem}.csv"


def unique_upload_path(filename: str) -> Path:
    CSV_UPLOAD_DIR.mkdir(exist_ok=True)
    safe_name = safe_upload_name(filename)
    path = CSV_UPLOAD_DIR / safe_name
    if not path.exists():
        return path
    stem = path.stem
    for index in range(2, 1000):
        candidate = CSV_UPLOAD_DIR / f"{stem}_{index}.csv"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Too many files with the same name.")


@app.post("/api/csv-files")
async def upload_csv_file(file: UploadFile = File(...)) -> dict:
    path = unique_upload_path(file.filename or "contacts.csv")
    content = await file.read(MAX_CSV_UPLOAD_BYTES + 1)
    if len(content) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV file is larger than 10 MB.")
    path.write_bytes(content)
    try:
        contacts = load_contacts(path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"CSV could not be loaded: {exc}") from exc
    return {
        "file": {
            "name": csv_file_id(path),
            "display_name": path.name,
            "path": str(path),
            "default": False,
            "uploaded": True,
        },
        "count": len(contacts),
    }


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
        interval_jitter_minutes=payload.interval_jitter_minutes,
        daily_send_limit=payload.daily_send_limit,
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
