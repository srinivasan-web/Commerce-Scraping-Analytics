from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import Header, HTTPException

from backend.app.schemas import ApiKey, ApiKeyCreate, AuthSession, LoginRequest


AUTH_STATE_PATH = Path("output/auth_store.json")


@dataclass
class Organization:
    id: str
    name: str
    users: set[str] = field(default_factory=set)


class AuthStore:
    def __init__(self) -> None:
        self.organizations: dict[str, Organization] = {}
        self.sessions: dict[str, AuthSession] = {}
        self.api_keys: dict[str, ApiKey] = {}
        self.load()

    def load(self) -> None:
        if not AUTH_STATE_PATH.exists():
            return
        try:
            payload = json.loads(AUTH_STATE_PATH.read_text(encoding="utf-8"))
            self.organizations = {
                org["id"]: Organization(id=org["id"], name=org["name"], users=set(org.get("users", [])))
                for org in payload.get("organizations", [])
            }
            self.api_keys = {
                item["key"]: ApiKey(
                    id=item["id"],
                    organization_id=item["organization_id"],
                    name=item["name"],
                    key_preview=item["key_preview"],
                    key=item["key"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                    active=item.get("active", True),
                )
                for item in payload.get("api_keys", [])
            }
        except Exception:
            self.organizations = {}
            self.api_keys = {}

    def save(self) -> None:
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "organizations": [
                {"id": org.id, "name": org.name, "users": sorted(org.users)}
                for org in self.organizations.values()
            ],
            "api_keys": [
                {
                    "id": key.id,
                    "organization_id": key.organization_id,
                    "name": key.name,
                    "key_preview": key.key_preview,
                    "key": key.key,
                    "created_at": key.created_at.isoformat(),
                    "active": key.active,
                }
                for key in self.api_keys.values()
            ],
        }
        AUTH_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _token(self, prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(32)}"

    def login(self, request: LoginRequest) -> AuthSession:
        org_name = request.organization.strip() or "Default Organization"
        normalized = org_name.lower()
        organization = next((org for org in self.organizations.values() if org.name.lower() == normalized), None)
        if not organization:
            organization = Organization(id=f"org_{uuid.uuid4().hex[:12]}", name=org_name)
            self.organizations[organization.id] = organization
        organization.users.add(request.email.lower())

        existing_key = next((key for key in self.api_keys.values() if key.organization_id == organization.id and key.active), None)
        if not existing_key:
            existing_key = self.create_api_key(organization.id, ApiKeyCreate(name="Default Dashboard Key"))

        session = AuthSession(
            access_token=self._token("sess"),
            organization_id=organization.id,
            organization_name=organization.name,
            user_email=request.email.lower(),
            api_key=existing_key.key,
        )
        self.sessions[session.access_token] = session
        self.save()
        return session

    def create_api_key(self, organization_id: str, request: ApiKeyCreate) -> ApiKey:
        raw_key = self._token("ak")
        api_key = ApiKey(
            id=f"key_{uuid.uuid4().hex[:12]}",
            organization_id=organization_id,
            name=request.name,
            key=raw_key,
            key_preview=f"{raw_key[:8]}...{raw_key[-6:]}",
            created_at=datetime.utcnow(),
        )
        self.api_keys[raw_key] = api_key
        self.save()
        return api_key

    def list_api_keys(self, organization_id: str) -> list[ApiKey]:
        return [key for key in self.api_keys.values() if key.organization_id == organization_id]

    def authenticate(self, authorization: str | None, api_key: str | None) -> AuthSession:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            session = self.sessions.get(token)
            if session:
                return session
        if api_key:
            key = self.api_keys.get(api_key)
            if key and key.active:
                organization = self.organizations.get(key.organization_id)
                return AuthSession(
                    access_token="",
                    organization_id=key.organization_id,
                    organization_name=organization.name if organization else key.organization_id,
                    user_email="api-key-user",
                    api_key=key.key,
                )
        raise HTTPException(status_code=401, detail="Authentication required. Sign in or send X-API-Key.")


auth_store = AuthStore()


async def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> AuthSession:
    return auth_store.authenticate(authorization, x_api_key)
