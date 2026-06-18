from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from html import escape
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .contacts import (
    email_domain,
    is_personal_email,
    load_contacts,
    manual_contacts,
    normalize_email,
    parse_age,
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
    template_ids: list[str] = Field(default_factory=list, max_length=20)
    csv_file: str | None = None
    content_type: Literal["Text", "HTML"] = "Text"
    override_contacted: bool = False
    exclude_company_emails: bool = True
    gender_filter: Literal["male", "female", "all"] = "male"
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    manual_recipients: list[str] = Field(default_factory=list, max_length=10000)
    manual_only: bool = False


class QueueRequest(PreviewRequest):
    campaign_name: str = Field(default="Untitled Campaign", min_length=1, max_length=120)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    selected_row_indexes: list[int] | None = None
    send_limit: int | None = Field(default=None, ge=1, le=10000)
    interval_minutes: int = Field(default=10, ge=1, le=1440)
    interval_jitter_minutes: int = Field(default=2, ge=0, le=1440)
    daily_send_limit: int = Field(default=25, ge=1, le=10000)
    max_failures: int = Field(default=3, ge=1, le=10000)
    auto_pause_on_failure: bool = True
    business_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    business_end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = "America/Chicago"


class SendTestRequest(BaseModel):
    to_email: str = Field(min_length=3)
    subject: str = "CSV Email Assistant live verification"
    body: str = "This is a controlled live-send verification from the local CSV Email Assistant."
    content_type: Literal["Text", "HTML"] = "Text"


class SuppressionRequest(BaseModel):
    email: str = Field(min_length=3)
    reason: Literal["manual", "unsubscribed", "bounced", "blocked", "complained", "replied_stop"] = "manual"
    note: str | None = None


class ReplyResponseRequest(BaseModel):
    body: str = Field(min_length=1)


class ReplySyncRequest(BaseModel):
    csv_file: str | None = None
    limit: int = Field(default=15, ge=1, le=100)


class TemplateRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


class GmailAccountRequest(BaseModel):
    email: str = Field(min_length=3)
    app_password: str = Field(min_length=8)
    activate: bool = True
    verify: bool = True


class SchedulingSettingsRequest(BaseModel):
    scheduling_url: str = Field(default="", max_length=500)


app = FastAPI(title="CSV Email Assistant")
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
_stop_event: asyncio.Event | None = None
_scheduler_task: asyncio.Task | None = None
CSV_UPLOAD_DIR = ROOT_DIR / "uploaded_csv"
ATTACHMENT_UPLOAD_DIR = ROOT_DIR / "uploaded_attachments"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024
SCHEDULING_URL_KEY = "scheduling_url"
CALENDLY_SIGNING_KEY = "calendly_webhook_signing_key"
CALENDLY_WEBHOOK_PATH = "/api/calendly/webhook"


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


def public_account(account: dict) -> dict:
    return {
        "id": account["id"],
        "email": account["email"],
        "is_active": bool(account["is_active"]),
        "created_at": account["created_at"],
    }


@app.get("/api/accounts")
def accounts() -> dict:
    return {
        "accounts": [public_account(account) for account in db.list_gmail_accounts()],
        "env_fallback": {
            "email": settings.from_email or settings.smtp_username or None,
            "configured": bool(settings.smtp_username.strip() and settings.smtp_password.strip()),
        },
    }


@app.post("/api/accounts")
def add_account(payload: GmailAccountRequest) -> dict:
    email = payload.email.strip().lower()
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid Gmail address.")
    if any(account["email"] == email for account in db.list_gmail_accounts()):
        raise HTTPException(status_code=409, detail="That Gmail account is already added.")
    app_password = payload.app_password.replace(" ", "")
    if payload.verify:
        try:
            mail_client().verify_login(email, app_password)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Gmail rejected the credentials: {exc}. Use a Google App Password, not the regular account password.",
            ) from exc
    account = db.add_gmail_account(email, app_password, activate=payload.activate)
    return {"account": public_account(account)}


@app.post("/api/accounts/deactivate")
def deactivate_accounts() -> dict:
    db.deactivate_gmail_accounts()
    return {"ok": True}


@app.post("/api/accounts/{account_id}/activate")
def activate_account(account_id: str) -> dict:
    account = db.set_active_gmail_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"account": public_account(account)}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str) -> dict:
    if not db.delete_gmail_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"deleted": True, "id": account_id}


@app.get("/api/settings/scheduling")
def scheduling_settings() -> dict:
    return {"scheduling_url": db.get_app_setting(SCHEDULING_URL_KEY, "")}


@app.post("/api/settings/scheduling")
def update_scheduling_settings(payload: SchedulingSettingsRequest) -> dict:
    url = payload.scheduling_url.strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Enter a full scheduling URL starting with https://")
    db.set_app_setting(SCHEDULING_URL_KEY, url)
    return {"scheduling_url": url}


def verify_calendly_signature(signing_key: str, header: str, body: bytes) -> bool:
    """Validates Calendly's 'Calendly-Webhook-Signature: t=<ts>,v1=<hmac>' header."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    except ValueError:
        return False
    timestamp = parts.get("t", "")
    expected = parts.get("v1", "")
    if not timestamp or not expected:
        return False
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    digest = hmac.new(signing_key.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


@app.post(CALENDLY_WEBHOOK_PATH)
async def calendly_webhook(request: Request) -> dict:
    raw = await request.body()
    signing_key = db.get_app_setting(CALENDLY_SIGNING_KEY, "")
    if signing_key:
        signature = request.headers.get("Calendly-Webhook-Signature", "")
        if not verify_calendly_signature(signing_key, signature, raw):
            raise HTTPException(status_code=401, detail="Invalid Calendly webhook signature.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    event_kind = str(data.get("event") or "")
    if event_kind not in {"invitee.created", "invitee.canceled"}:
        return {"ok": True, "ignored": event_kind}

    payload = data.get("payload") or {}
    scheduled = payload.get("scheduled_event") or {}
    created = db.record_calendly_booking(
        event_kind=event_kind,
        invitee_name=str(payload.get("name") or ""),
        invitee_email=str(payload.get("email") or ""),
        event_name=str(scheduled.get("name") or ""),
        event_start=str(scheduled.get("start_time") or ""),
        invitee_uri=str(payload.get("uri") or ""),
    )
    return {"ok": True, "recorded": created}


@app.get("/api/calendly/bookings")
def calendly_bookings(limit: int = 20) -> dict:
    return {
        "bookings": db.list_calendly_bookings(limit),
        "unread": db.count_unread_calendly_bookings(),
    }


@app.post("/api/calendly/bookings/read")
def mark_calendly_bookings_read() -> dict:
    db.mark_calendly_bookings_read()
    return {"ok": True, "unread": 0}


class CalendlyWebhookSettingsRequest(BaseModel):
    signing_key: str = Field(default="", max_length=300)


@app.get("/api/settings/calendly-webhook")
def calendly_webhook_settings() -> dict:
    return {
        "configured": bool(db.get_app_setting(CALENDLY_SIGNING_KEY, "")),
        "webhook_path": CALENDLY_WEBHOOK_PATH,
    }


@app.post("/api/settings/calendly-webhook")
def update_calendly_webhook_settings(payload: CalendlyWebhookSettingsRequest) -> dict:
    db.set_app_setting(CALENDLY_SIGNING_KEY, payload.signing_key.strip())
    return {"configured": bool(payload.signing_key.strip())}


@app.get("/api/templates")
def templates() -> dict:
    return {"templates": db.list_templates()}


@app.post("/api/templates")
def save_template(payload: TemplateRequest) -> dict:
    return {
        "template": db.save_template(
            name=payload.name,
            subject=payload.subject,
            body=payload.body,
            template_id=payload.id,
        )
    }


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: str) -> dict:
    if not db.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"deleted": True, "id": template_id}


def csv_file_id(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def available_csv_files() -> list[dict[str, str | bool]]:
    paths = []
    if settings.default_csv_path.exists():
        paths.append(settings.default_csv_path)
    if CSV_UPLOAD_DIR.exists():
        paths.extend(sorted(CSV_UPLOAD_DIR.glob("*.csv")))
    seen: set[Path] = set()
    unique_paths = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    return [
        {
            "name": csv_file_id(path),
            "display_name": path.name,
            "path": str(path),
            "default": path.resolve() == settings.default_csv_path.resolve(),
            "uploaded": path.parent == CSV_UPLOAD_DIR,
        }
        for path in unique_paths
    ]


def selected_csv_path(csv_file: str | None = None):
    csv_files = {item["name"]: item["path"] for item in available_csv_files()}
    if not csv_file:
        return settings.default_csv_path
    if csv_file not in csv_files:
        raise HTTPException(status_code=400, detail="Unknown CSV file.")
    return Path(csv_files[csv_file])


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


def safe_attachment_name(filename: str) -> str:
    base = Path(filename or "attachment").name
    stem = Path(base).stem or "attachment"
    suffix = Path(base).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "attachment"
    safe_suffix = re.sub(r"[^A-Za-z0-9.]+", "", suffix)[:20]
    return f"{safe_stem}{safe_suffix}"


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


def unique_attachment_path(filename: str) -> Path:
    ATTACHMENT_UPLOAD_DIR.mkdir(exist_ok=True)
    safe_name = safe_attachment_name(filename)
    path = ATTACHMENT_UPLOAD_DIR / safe_name
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = ATTACHMENT_UPLOAD_DIR / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Too many files with the same name.")


def attachment_file_id(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def available_attachments() -> list[dict[str, str | int]]:
    if not ATTACHMENT_UPLOAD_DIR.exists():
        return []
    files = sorted(path for path in ATTACHMENT_UPLOAD_DIR.iterdir() if path.is_file())
    return [
        {
            "id": attachment_file_id(path),
            "name": path.name,
            "size": path.stat().st_size,
            "path": str(path),
        }
        for path in files
    ]


def selected_attachment_paths(attachment_ids: list[str]) -> list[Path]:
    available = {item["id"]: Path(str(item["path"])) for item in available_attachments()}
    paths = []
    total_size = 0
    for attachment_id in attachment_ids:
        path = available.get(attachment_id)
        if not path:
            raise HTTPException(status_code=400, detail=f"Unknown attachment: {attachment_id}")
        size = path.stat().st_size
        total_size += size
        if size > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail=f"{path.name} is larger than 10 MB.")
        paths.append(path)
    if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="Attachments are larger than 20 MB total.")
    return paths


@app.post("/api/csv-files")
async def upload_csv_file(file: UploadFile = File(...)) -> dict:
    path = unique_upload_path(file.filename or "contacts.csv")
    content = await file.read()
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


@app.get("/api/attachments")
def attachments() -> dict:
    return {"files": available_attachments()}


@app.post("/api/attachments")
async def upload_attachments(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one attachment.")
    saved = []
    total_size = 0
    try:
        for file in files:
            path = unique_attachment_path(file.filename or "attachment")
            content = await file.read(MAX_ATTACHMENT_BYTES + 1)
            if len(content) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(status_code=413, detail=f"{file.filename} is larger than 10 MB.")
            total_size += len(content)
            if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
                raise HTTPException(status_code=413, detail="Attachments are larger than 20 MB total.")
            path.write_bytes(content)
            saved.append(path)
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    return {
        "files": [
            {
                "id": attachment_file_id(path),
                "name": path.name,
                "size": path.stat().st_size,
                "path": str(path),
            }
            for path in saved
        ]
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


def rotation_templates(payload: PreviewRequest) -> list[dict]:
    """Templates cycled across recipients; fewer than 2 selections falls back to the inline editor."""
    if len(payload.template_ids) < 2:
        return [{"name": None, "subject": payload.subject, "body": payload.body}]
    templates = []
    for template_id in payload.template_ids:
        template = db.get_template(template_id)
        if not template:
            raise HTTPException(status_code=400, detail="A template selected for rotation no longer exists.")
        templates.append({"name": template["name"], "subject": template["subject"], "body": template["body"]})
    return templates


def build_scheduling_link(base_url: str, contact) -> str:
    """Append URL-encoded name/email so the recipient's Calendly form opens pre-filled."""
    base = (base_url or "").strip()
    if not base:
        return ""
    full_name = " ".join(part for part in (contact.first_name, contact.last_name) if part).strip()
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query))
    if full_name:
        query["name"] = full_name
    if contact.email:
        query["email"] = contact.email
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


SCHEDULE_BUTTON_LABEL = "Schedule a call"
BUTTON_SENTINEL = "\x00CALENDLY_BUTTON\x00"
# Both {{calendly_button}} and {{calendly_link}} render the scheduling button so users
# get the same result regardless of which variable they reach for.
BUTTON_PLACEHOLDER_RE = re.compile(r"{{\s*calendly_(?:button|link)\s*}}")


def uses_calendly_button(text: str) -> bool:
    return bool(BUTTON_PLACEHOLDER_RE.search(text or ""))


def calendly_button_html(link: str) -> str:
    """Email-safe button with inline styles (external stylesheets are stripped by mail clients)."""
    return (
        f'<a href="{escape(link, quote=True)}" '
        'style="display:inline-block;background-color:#10b981;color:#ffffff;'
        "text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;"
        'font-family:Arial,Helvetica,sans-serif;font-size:15px;">'
        f"{SCHEDULE_BUTTON_LABEL}</a>"
    )


def render_email_body(body_template: str, values: dict, link: str, as_html: bool) -> tuple[str, list[str]]:
    if not as_html:
        text_values = {**values, "calendly_link": link, "calendly_button": link}
        return render_template(body_template, text_values)
    button_value = BUTTON_SENTINEL if link else ""
    html_values = {**values, "calendly_link": button_value, "calendly_button": button_value}
    rendered, missing = render_template(body_template, html_values)
    html = escape(rendered).replace("\n", "<br>\n").replace(BUTTON_SENTINEL, calendly_button_html(link))
    return html, missing


def build_preview(payload: PreviewRequest) -> dict:
    if payload.age_min is not None and payload.age_max is not None and payload.age_min > payload.age_max:
        raise HTTPException(status_code=400, detail="Minimum age cannot be greater than maximum age.")
    templates = rotation_templates(payload)
    scheduling_url = db.get_app_setting(SCHEDULING_URL_KEY, "")
    use_html = any(uses_calendly_button(template["body"]) for template in templates)
    manual = manual_contacts(payload.manual_recipients)
    contacts = []
    if not payload.manual_only:
        try:
            contacts.extend(load_contacts(selected_csv_path(payload.csv_file)))
        except HTTPException:
            if not manual:
                raise
    contacts.extend(manual)
    contacted = db.contacted_emails()
    suppressed = db.suppressed_emails()
    seen: set[str] = set()
    rows = []
    summary = {
        "total": len(contacts),
        "sendable": 0,
        "invalid": 0,
        "already_contacted": 0,
        "duplicates": 0,
        "suppressed": 0,
        "age_filtered": 0,
        "company_filtered": 0,
        "gender_filtered": 0,
    }
    for index, contact in enumerate(contacts):
        template = templates[index % len(templates)]
        errors = validate_contact(contact)
        age = parse_age(contact.age)
        gender = contact.gender.strip().lower()
        gender_matches = (
            payload.gender_filter == "all"
            or (payload.gender_filter == "male" and gender in {"m", "male", "man"})
            or (payload.gender_filter == "female" and gender in {"f", "female", "woman"})
        )
        outside_age_range = (
            age is not None
            and (
                (payload.age_min is not None and age < payload.age_min)
                or (payload.age_max is not None and age > payload.age_max)
            )
        )
        link = build_scheduling_link(scheduling_url, contact)
        subject_values = {**contact.row_data, "calendly_link": link, "calendly_button": link}
        subject, missing_subject = render_template(template["subject"], subject_values)
        body, missing_body = render_email_body(template["body"], dict(contact.row_data), link, use_html)
        email_norm = normalize_email(contact.email)
        company_email = bool(email_norm and is_valid_email(contact.email) and not is_personal_email(contact.email))
        already_contacted = email_norm in contacted
        suppression = suppressed.get(email_norm)
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
        if suppression:
            errors.append(f"suppressed_{suppression['reason']}")
            summary["suppressed"] += 1
        if outside_age_range:
            errors.append("outside_age_range")
            summary["age_filtered"] += 1
        if payload.exclude_company_emails and company_email:
            errors.append("company_email")
            summary["company_filtered"] += 1
        if not gender_matches and gender != "__manual__":
            errors.append("gender_filtered")
            summary["gender_filtered"] += 1
        sendable = not errors
        summary["sendable" if sendable else "invalid"] += 1
        rows.append(
            {
                "row_index": contact.row_index,
                "email": contact.email,
                "email_norm": email_norm,
                "email_domain": email_domain(contact.email),
                "email_type": "company" if company_email else "personal",
                "gender": contact.gender,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "subject": subject,
                "body": body,
                "template_name": template["name"],
                "missing_variables": missing,
                "already_contacted": already_contacted,
                "suppressed": bool(suppression),
                "suppression_reason": suppression["reason"] if suppression else None,
                "duplicate_in_csv": duplicate_in_csv,
                "errors": errors,
                "sendable": sendable,
                "row_data": contact.row_data,
            }
        )
    return {"summary": summary, "rows": rows, "content_type": "HTML" if use_html else payload.content_type}


def csv_contact_email_norms(csv_file: str | None = None) -> set[str]:
    try:
        contacts = load_contacts(selected_csv_path(csv_file))
    except Exception:
        return set()
    return {normalize_email(contact.email) for contact in contacts if normalize_email(contact.email)}


@app.post("/api/preview")
def preview(payload: PreviewRequest) -> dict:
    return build_preview(payload)


@app.post("/api/jobs")
def create_job(payload: QueueRequest) -> dict:
    rotation = rotation_templates(payload)
    preview_data = build_preview(payload)
    selected_attachment_paths(payload.attachment_ids)  # validates ids and size limits
    items = [row for row in preview_data["rows"] if row["sendable"]]
    if payload.selected_row_indexes is not None:
        selected = set(payload.selected_row_indexes)
        items = [row for row in items if row["row_index"] in selected]
    if payload.send_limit is not None:
        items = items[: payload.send_limit]
    if not items:
        raise HTTPException(status_code=400, detail="No sendable contacts after validation.")
    job_id = db.create_job(
        campaign_name=payload.campaign_name.strip(),
        items=items,
        interval_minutes=payload.interval_minutes,
        interval_jitter_minutes=payload.interval_jitter_minutes,
        daily_send_limit=payload.daily_send_limit,
        max_failures=payload.max_failures,
        auto_pause_on_failure=payload.auto_pause_on_failure,
        business_start=payload.business_start,
        business_end=payload.business_end,
        timezone_name=payload.timezone,
        override_contacted=payload.override_contacted,
        content_type=preview_data.get("content_type", payload.content_type),
        attachment_files=list(payload.attachment_ids),
        template_rotation=[template["name"] for template in rotation if template["name"]],
    )
    return {"job_id": job_id, "queued": len(items), "summary": preview_data["summary"]}


@app.get("/api/jobs")
def jobs() -> dict:
    return {"jobs": db.list_jobs()}


@app.get("/api/email-status-summary")
def email_status_summary() -> dict:
    return db.email_status_summary()


@app.get("/api/replies")
def replies(csv_file: str | None = None) -> dict:
    allowed = csv_contact_email_norms(csv_file)
    return {
        "replies": [
            reply for reply in db.list_replies()
            if not allowed or reply["from_email_norm"] in allowed
        ]
    }


@app.post("/api/replies/sync")
def sync_replies(payload: ReplySyncRequest | None = None) -> dict:
    try:
        inbound = mail_client().fetch_inbound_replies(limit=payload.limit if payload else 15)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gmail reply sync failed: {exc}") from exc
    allowed = csv_contact_email_norms(payload.csv_file if payload else None)
    saved = []
    skipped = 0
    for reply in inbound:
        from_email_norm = normalize_email(reply.from_email)
        matched = db.queue_item_for_reply(reply.references, from_email_norm)
        if allowed and from_email_norm not in allowed and not matched:
            skipped += 1
            continue
        saved_reply = db.record_inbound_reply(
            message_id=reply.message_id,
            from_email=reply.from_email,
            from_email_norm=from_email_norm,
            subject=reply.subject,
            body=reply.body,
            received_at=reply.received_at,
            references=reply.references,
        )
        if saved_reply:
            saved.append(saved_reply)
    return {
        "synced": len(saved),
        "skipped": skipped,
        "replies": [
            reply for reply in db.list_replies()
            if not allowed or reply["from_email_norm"] in allowed
        ],
    }


@app.post("/api/replies/{reply_id}/respond")
def respond_to_reply(reply_id: int, payload: ReplyResponseRequest) -> dict:
    reply = db.get_reply(reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found.")
    try:
        result = mail_client().send_mail(
            to_email=reply["from_email"],
            subject=f"Re: {reply['subject'] or 'Your reply'}",
            body=payload.body,
            content_type="Text",
            extra_headers={
                "In-Reply-To": reply["message_id"],
                "References": reply["message_id"],
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Reply send failed: {exc}") from exc
    updated = db.mark_reply_responded(reply_id, payload.body)
    return {"ok": True, "reply": updated, "result": result.as_dict()}


@app.get("/api/jobs/{job_id}/queue")
def queue(job_id: str) -> dict:
    return {"items": db.list_queue(job_id)}


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict:
    db.set_job_status(job_id, "paused", "Paused by user.")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    db.set_job_status(job_id, "running")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    db.set_job_status(job_id, "cancelled")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    # Stop any pending sends before removing; queue items cascade with the job.
    db.set_job_status(job_id, "cancelled")
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"deleted": True, "id": job_id}


@app.get("/api/suppressions")
def suppressions() -> dict:
    return {"contacts": db.suppression_history()}


@app.post("/api/suppressions")
def create_suppression(payload: SuppressionRequest) -> dict:
    if not is_valid_email(payload.email):
        raise HTTPException(status_code=400, detail="Enter a valid email address to suppress.")
    email_norm = normalize_email(payload.email)
    db.suppress_email(
        payload.email,
        email_norm,
        payload.reason,
        "manual",
        payload.note.strip() if payload.note else None,
    )
    return {"ok": True, "email": payload.email, "email_norm": email_norm, "reason": payload.reason}


@app.delete("/api/suppressions/{email}")
def delete_suppression(email: str) -> dict:
    email_norm = normalize_email(email)
    removed = db.unsuppress_email(email_norm)
    if not removed:
        raise HTTPException(status_code=404, detail="Suppressed contact not found.")
    return {"ok": True, "email_norm": email_norm}
