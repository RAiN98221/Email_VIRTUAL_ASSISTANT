from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "first_name",
    "last_name",
    "email",
    "phone",
    "city",
    "state",
    "gender",
}
EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "zoho.com",
    "yandex.com",
    "gmx.com",
    "mail.com",
    "fastmail.com",
    "tutanota.com",
    "comcast.net",
    "verizon.net",
    "att.net",
    "sbcglobal.net",
    "bellsouth.net",
    "cox.net",
    "charter.net",
    "spectrum.net",
    "earthlink.net",
    "roadrunner.com",
}


@dataclass(frozen=True)
class Contact:
    row_index: int
    first_name: str
    last_name: str
    email: str
    phone: str
    city: str
    state: str
    birth_date: str
    age: str
    gender: str

    @property
    def row_data(self) -> dict[str, str]:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "city": self.city,
            "state": self.state,
            "birth_date": self.birth_date,
            "age": self.age,
            "gender": self.gender,
        }


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def email_domain(email: str) -> str:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return ""
    return normalized.rsplit("@", 1)[1]


def is_personal_email(email: str) -> bool:
    return email_domain(email) in PERSONAL_EMAIL_DOMAINS


def parse_age(age: str) -> float | None:
    try:
        return float(str(age).strip())
    except (TypeError, ValueError):
        return None


def load_contacts(path: Path) -> list[Contact]:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        contacts = []
        for index, row in enumerate(reader, start=2):
            contacts.append(
                Contact(
                    row_index=index,
                    first_name=(row.get("first_name") or "").strip(),
                    last_name=(row.get("last_name") or "").strip(),
                    email=(row.get("email") or "").strip(),
                    phone=(row.get("phone") or "").strip(),
                    city=(row.get("city") or "").strip(),
                    state=(row.get("state") or "").strip(),
                    birth_date=(row.get("birth_date") or "").strip(),
                    age=(row.get("age") or "").strip(),
                    gender=(row.get("gender") or "").strip(),
                )
            )
        return contacts


def manual_contacts(entries: list[str], *, start_row: int = 1_000_000) -> list[Contact]:
    contacts: list[Contact] = []
    for offset, raw_entry in enumerate(entries):
        entry = (raw_entry or "").strip()
        if not entry:
            continue
        name = ""
        email = entry
        bracket_match = re.match(r"^\s*(.*?)\s*<([^<>@\s]+@[^<>\s]+)>\s*$", entry)
        if bracket_match:
            name = bracket_match.group(1).strip().strip('"')
            email = bracket_match.group(2).strip()
        else:
            email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", entry, re.IGNORECASE)
            if email_match:
                email = email_match.group(0)
                name = entry.replace(email_match.group(0), "").strip(" ,<>\"")
        local_part = email.split("@", 1)[0] if "@" in email else email
        inferred_name = name or local_part.replace(".", " ").replace("_", " ").replace("-", " ")
        parts = [part for part in inferred_name.split() if part]
        first_name = parts[0].title() if parts else ""
        last_name = " ".join(parts[1:]).title() if len(parts) > 1 else ""
        contacts.append(
            Contact(
                row_index=start_row + offset,
                first_name=first_name,
                last_name=last_name,
                email=email.strip(),
                phone="",
                city="",
                state="",
                birth_date="",
                age="",
                gender="__manual__",
            )
        )
    return contacts


def validate_contact(contact: Contact) -> list[str]:
    errors: list[str] = []
    if not is_valid_email(contact.email):
        errors.append("invalid_email")
    age = parse_age(contact.age)
    if age is not None and age < 18:
        errors.append("under_18")
    return errors


def render_template(template: str, values: dict[str, Any]) -> tuple[str, list[str]]:
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None or value == "":
            missing.add(key)
            return ""
        return str(value)

    return PLACEHOLDER_RE.sub(replace, template or ""), sorted(missing)
