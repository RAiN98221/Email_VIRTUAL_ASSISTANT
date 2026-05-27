from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_connect_host: str = os.getenv("SMTP_CONNECT_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    from_email: str = os.getenv("FROM_EMAIL", os.getenv("SMTP_USERNAME", ""))
    imap_host: str = os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_port: int = int(os.getenv("IMAP_PORT", "993"))
    imap_username: str = os.getenv("IMAP_USERNAME", os.getenv("SMTP_USERNAME", ""))
    imap_password: str = os.getenv("IMAP_PASSWORD", os.getenv("SMTP_PASSWORD", ""))
    verify_sent_mail: bool = os.getenv("VERIFY_SENT_MAIL", "true").lower() in {"1", "true", "yes", "on"}
    verify_sent_timeout_seconds: int = int(os.getenv("VERIFY_SENT_TIMEOUT_SECONDS", "20"))
    verify_sent_poll_seconds: int = int(os.getenv("VERIFY_SENT_POLL_SECONDS", "2"))
    database_path: Path = ROOT_DIR / os.getenv("APP_DATABASE_PATH", "email_assistant.sqlite3")
    default_csv_path: Path = ROOT_DIR / os.getenv(
        "DEFAULT_CSV_PATH", "filtered_contacts_under35_male_FIXED.csv"
    )


settings = Settings()
