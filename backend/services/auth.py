"""Authentication, authorization, and audit helpers for the platform API."""

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from db import engine

SESSION_DAYS = int(os.environ.get("AUTH_SESSION_DAYS", "7"))
_security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    display_name: str
    is_platform_admin: bool


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(password: str) -> str:
    """Create a self-contained scrypt password hash using the stdlib."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(conn, user_id: str) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await conn.execute(
        text(
            "INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, created_at) "
            "VALUES (:id, :user_id, :token_hash, :expires_at, NOW())"
        ),
        {
            "id": new_id(),
            "user_id": user_id,
            "token_hash": hash_session_token(token),
            "expires_at": expires_at,
        },
    )
    return token, expires_at


async def audit(
    conn,
    *,
    action: str,
    actor_user_id: str | None,
    resource_type: str,
    resource_id: str | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
    details: dict | None = None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO audit_logs "
            "(id, actor_user_id, organization_id, project_id, action, resource_type, resource_id, details, created_at) "
            "VALUES (:id, :actor_user_id, :organization_id, :project_id, :action, "
            ":resource_type, :resource_id, CAST(:details AS jsonb), NOW())"
        ),
        {
            "id": new_id(),
            "actor_user_id": actor_user_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": __import__("json").dumps(details or {}),
        },
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    async with engine.connect() as conn:
        row = (await conn.execute(
            text(
                "SELECT u.id, u.email, u.display_name, u.is_platform_admin "
                "FROM auth_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL "
                "AND s.expires_at > NOW() AND u.is_active = true"
            ),
            {"token_hash": hash_session_token(credentials.credentials)},
        )).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired")
    return CurrentUser(id=row[0], email=row[1], display_name=row[2], is_platform_admin=row[3])


async def require_platform_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform administrator permission required")
    return user


async def require_project_member(
    user: CurrentUser = Depends(get_current_user),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
) -> CurrentUser:
    if user.is_platform_admin:
        return user
    async with engine.connect() as conn:
        count = (await conn.execute(
            text("SELECT COUNT(*) FROM memberships WHERE user_id = :user_id"),
            {"user_id": user.id},
        )).scalar_one()
        if project_id is None and count > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Project-ID is required for multi-project users")
        if project_id:
            row = (await conn.execute(
                text("SELECT 1 FROM memberships WHERE user_id = :user_id AND project_id = :project_id LIMIT 1"),
                {"user_id": user.id, "project_id": project_id},
            )).fetchone()
        else:
            row = (await conn.execute(
                text("SELECT 1 FROM memberships WHERE user_id = :user_id LIMIT 1"),
                {"user_id": user.id},
            )).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project membership required")
    return user


async def require_project_editor(
    user: CurrentUser = Depends(get_current_user),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
) -> CurrentUser:
    if user.is_platform_admin:
        return user
    async with engine.connect() as conn:
        count = (await conn.execute(
            text("SELECT COUNT(*) FROM memberships WHERE user_id = :user_id"),
            {"user_id": user.id},
        )).scalar_one()
        if project_id is None and count > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Project-ID is required for multi-project users")
        if project_id:
            row = (await conn.execute(
                text("SELECT role FROM memberships WHERE user_id = :user_id AND project_id = :project_id "
                     "ORDER BY CASE WHEN role = 'editor' THEN 0 ELSE 1 END LIMIT 1"),
                {"user_id": user.id, "project_id": project_id},
            )).fetchone()
        else:
            row = (await conn.execute(
                text("SELECT role FROM memberships WHERE user_id = :user_id "
                     "ORDER BY CASE WHEN role = 'editor' THEN 0 ELSE 1 END LIMIT 1"),
                {"user_id": user.id},
            )).fetchone()
    if row is None or row[0] != "editor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor permission required")
    return user


async def require_project_role(project_id: str, user: CurrentUser, allowed_roles: set[str]) -> str:
    if user.is_platform_admin:
        return "platform_admin"
    async with engine.connect() as conn:
        row = (await conn.execute(
            text(
                "SELECT role FROM memberships "
                "WHERE user_id = :user_id AND project_id = :project_id"
            ),
            {"user_id": user.id, "project_id": project_id},
        )).fetchone()
    if row is None or row[0] not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project permission required")
    return row[0]


def project_clause(project_id: str | None, alias: str = "") -> tuple[str, dict]:
    """Return (SQL_AND_clause, params_dict) safe for asyncpg.

    Avoids the asyncpg-incompatible pattern ``:pid IS NULL OR col = :pid``
    by branching in Python instead of SQL.
    """
    col = f"{alias}.project_id" if alias else "project_id"
    if project_id:
        return (f" AND {col} = :project_id", {"project_id": project_id})
    return ("", {})
