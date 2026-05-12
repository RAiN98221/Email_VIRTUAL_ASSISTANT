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
    microsoft_client_id: str = os.getenv("MICROSOFT_CLIENT_ID", "")
    microsoft_tenant: str = os.getenv("MICROSOFT_TENANT", "common")
    microsoft_redirect_uri: str = os.getenv(
        "MICROSOFT_REDIRECT_URI", "http://localhost:8000/auth/callback"
    )
    database_path: Path = ROOT_DIR / os.getenv("APP_DATABASE_PATH", "email_assistant.sqlite3")
    default_csv_path: Path = ROOT_DIR / os.getenv(
        "DEFAULT_CSV_PATH", "filtered_contacts_under35_male_FIXED.csv"
    )
    token_cache_path: Path = ROOT_DIR / "msal_token_cache.bin"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.microsoft_tenant}"


settings = Settings()
