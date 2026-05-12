from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import msal
import requests

from .settings import settings


SCOPES = ["Mail.Send", "User.Read"]
GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
PLACEHOLDER_CLIENT_IDS = {"", "your-azure-app-client-id"}


class AuthNotConfigured(RuntimeError):
    pass


class AuthRequired(RuntimeError):
    pass


class GraphClient:
    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or settings.token_cache_path
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            self.cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        if not self.is_configured():
            self.app = None
        else:
            self.app = msal.PublicClientApplication(
                settings.microsoft_client_id,
                authority=settings.authority,
                token_cache=self.cache,
            )

    def _save_cache(self) -> None:
        if self.cache.has_state_changed:
            self.cache_path.write_text(self.cache.serialize(), encoding="utf-8")

    def is_configured(self) -> bool:
        return settings.microsoft_client_id.strip() not in PLACEHOLDER_CLIENT_IDS

    def auth_url(self) -> str:
        if not self.app:
            raise AuthNotConfigured("Set MICROSOFT_CLIENT_ID in .env first.")
        return self.app.get_authorization_request_url(
            scopes=SCOPES,
            redirect_uri=settings.microsoft_redirect_uri,
            prompt="select_account",
        )

    def acquire_token_by_code(self, code: str) -> dict[str, Any]:
        if not self.app:
            raise AuthNotConfigured("Set MICROSOFT_CLIENT_ID in .env first.")
        result = self.app.acquire_token_by_authorization_code(
            code,
            scopes=SCOPES,
            redirect_uri=settings.microsoft_redirect_uri,
        )
        self._save_cache()
        if "access_token" not in result:
            raise AuthRequired(json.dumps(result))
        return result

    def access_token(self) -> str:
        if not self.app:
            raise AuthNotConfigured("Set MICROSOFT_CLIENT_ID in .env first.")
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
            self._save_cache()
            if result and "access_token" in result:
                return result["access_token"]
        raise AuthRequired("Login with Microsoft before sending.")

    def auth_status(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"configured": False, "authenticated": False, "account": None}
        accounts = self.app.get_accounts() if self.app else []
        return {
            "configured": True,
            "authenticated": bool(accounts),
            "account": accounts[0].get("username") if accounts else None,
        }

    def send_mail(self, to_email: str, subject: str, body: str, content_type: str = "Text") -> str | None:
        token = self.access_token()
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if content_type.lower() == "html" else "Text",
                    "content": body,
                },
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": True,
        }
        response = requests.post(
            GRAPH_SENDMAIL_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if response.status_code not in (202, 200):
            raise RuntimeError(f"Graph sendMail failed {response.status_code}: {response.text}")
        return response.headers.get("request-id")
