"""Identity, project access-request, and audit APIs."""

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from db import engine
from services.auth import (
    CurrentUser,
    audit,
    create_session,
    get_current_user,
    hash_password,
    hash_session_token,
    new_id,
    require_platform_admin,
    require_project_role,
    verify_password,
)

logger = logging.getLogger(__name__)

_NETPULSE_ADMIN_EMAIL = os.environ.get("NETPULSE_ADMIN_EMAIL", "").strip().lower()

router = APIRouter(prefix="/api", tags=["identity"])


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("email must be valid")
        return email


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("email must be valid")
        return email


class OrganizationCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ProjectCreateIn(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=128)


class AccessRequestCreateIn(BaseModel):
    project_id: str
    requested_role: str
    reason: str | None = Field(default=None, max_length=1000)


class AccessRequestReviewIn(BaseModel):
    decision: str
    review_note: str | None = Field(default=None, max_length=1000)


def _user_data(user: CurrentUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_platform_admin": user.is_platform_admin,
    }


async def _auth_response(conn, user: CurrentUser) -> dict:
    token, expires_at = await create_session(conn, user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": _user_data(user),
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn):
    email = body.email
    async with engine.begin() as conn:
        # Serialize bootstrap-admin assignment so two simultaneous registrations
        # cannot both become the first platform administrator.
        await conn.execute(text("SELECT pg_advisory_xact_lock(8202401)"))
        exists = (await conn.execute(text("SELECT 1 FROM users WHERE email = :email"), {"email": email})).fetchone()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
        first_user = (await conn.execute(text("SELECT COUNT(*) FROM users"))).fetchone()[0] == 0
        # Determine if this user should be platform_admin.
        # If NETPULSE_ADMIN_EMAIL is set, only the matching email gets admin.
        # If unset, the first user becomes admin (backward-compat dev mode) with a warning.
        if _NETPULSE_ADMIN_EMAIL:
            is_admin = email == _NETPULSE_ADMIN_EMAIL
        else:
            is_admin = first_user
            if is_admin:
                logger.warning(
                    "NETPULSE_ADMIN_EMAIL is not set — first user '%s' becomes platform_admin. "
                    "Set NETPULSE_ADMIN_EMAIL in production.", email,
                )
        user = CurrentUser(new_id(), email, body.display_name.strip(), is_admin)
        await conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name, is_platform_admin, is_active, created_at) "
                "VALUES (:id, :email, :password_hash, :display_name, :is_platform_admin, true, NOW())"
            ),
            {**_user_data(user), "password_hash": hash_password(body.password)},
        )
        if first_user:
            organization_id = new_id()
            project_id = new_id()
            await conn.execute(
                text("INSERT INTO organizations (id, name, created_by, created_at) VALUES (:id, :name, :created_by, NOW())"),
                {"id": organization_id, "name": "NetPulse", "created_by": user.id},
            )
            await conn.execute(
                text("INSERT INTO projects (id, organization_id, name, created_at) VALUES (:id, :organization_id, :name, NOW())"),
                {"id": project_id, "organization_id": organization_id, "name": "Default"},
            )
            await conn.execute(
                text(
                    "INSERT INTO memberships (id, user_id, organization_id, project_id, role, created_at) "
                    "VALUES (:id, :user_id, :organization_id, :project_id, 'editor', NOW())"
                ),
                {"id": new_id(), "user_id": user.id, "organization_id": organization_id, "project_id": project_id},
            )
            # Backfill seeded monitoring resources to the bootstrap project.
            # Migrations seed endpoints, probes, links, alert_rules, and nodes before
            # any project exists, leaving project_id = NULL.  Without this backfill
            # the REST API returns zero rows after the ProjectSelector auto-selects
            # the first project.
            for table in (
                "nodes", "metrics", "alerts", "incidents", "chaos_events",
                "endpoints", "probe_metrics", "alert_rules", "packet_evidence",
            ):
                await conn.execute(
                    text(f"UPDATE {table} SET project_id = :pid WHERE project_id IS NULL"),
                    {"pid": project_id},
                )
            await audit(
                conn,
                action="project.bootstrap_created",
                actor_user_id=user.id,
                resource_type="project",
                resource_id=project_id,
                organization_id=organization_id,
                project_id=project_id,
                details={"bootstrap": True},
            )
        await audit(conn, action="user.registered", actor_user_id=user.id, resource_type="user", resource_id=user.id)
        payload = await _auth_response(conn, user)
    return {"success": True, "data": payload}


@router.post("/auth/login")
async def login(body: LoginIn):
    email = body.email
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT id, email, display_name, is_platform_admin, password_hash, is_active FROM users WHERE email = :email"),
            {"email": email},
        )).fetchone()
        if row is None or not row[5] or not verify_password(body.password, row[4]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        user = CurrentUser(id=row[0], email=row[1], display_name=row[2], is_platform_admin=row[3])
        await audit(conn, action="user.logged_in", actor_user_id=user.id, resource_type="user", resource_id=user.id)
        payload = await _auth_response(conn, user)
    return {"success": True, "data": payload}


@router.post("/auth/logout")
async def logout(
    user: CurrentUser = Depends(get_current_user),
    authorization: str | None = Header(default=None),
):
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE auth_sessions SET revoked_at = NOW() WHERE user_id = :user_id AND token_hash = :token_hash"),
            {"user_id": user.id, "token_hash": hash_session_token(authorization[7:])},
        )
        await audit(conn, action="user.logged_out", actor_user_id=user.id, resource_type="user", resource_id=user.id)
    return {"success": True, "data": {"user_id": user.id}}


@router.get("/auth/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return {"success": True, "data": _user_data(user)}


@router.post("/admin/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreateIn, user: CurrentUser = Depends(require_platform_admin)):
    organization_id = new_id()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO organizations (id, name, created_by, created_at) VALUES (:id, :name, :created_by, NOW())"),
            {"id": organization_id, "name": body.name.strip(), "created_by": user.id},
        )
        await audit(conn, action="organization.created", actor_user_id=user.id, resource_type="organization", resource_id=organization_id, organization_id=organization_id)
    return {"success": True, "data": {"id": organization_id, "name": body.name.strip()}}


@router.post("/admin/projects", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreateIn, user: CurrentUser = Depends(require_platform_admin)):
    project_id = new_id()
    async with engine.begin() as conn:
        org = (await conn.execute(text("SELECT 1 FROM organizations WHERE id = :id"), {"id": body.organization_id})).fetchone()
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        await conn.execute(
            text("INSERT INTO projects (id, organization_id, name, created_at) VALUES (:id, :organization_id, :name, NOW())"),
            {"id": project_id, "organization_id": body.organization_id, "name": body.name.strip()},
        )
        await audit(conn, action="project.created", actor_user_id=user.id, resource_type="project", resource_id=project_id, organization_id=body.organization_id, project_id=project_id)
    return {"success": True, "data": {"id": project_id, "organization_id": body.organization_id, "name": body.name.strip()}}


@router.get("/projects")
async def list_projects(user: CurrentUser = Depends(get_current_user)):
    async with engine.connect() as conn:
        if user.is_platform_admin:
            rows = (await conn.execute(text("SELECT p.id, p.name, o.id, o.name, 'platform_admin' FROM projects p JOIN organizations o ON o.id = p.organization_id ORDER BY o.name, p.name"))).fetchall()
        else:
            rows = (await conn.execute(text("SELECT p.id, p.name, o.id, o.name, m.role FROM memberships m JOIN projects p ON p.id = m.project_id JOIN organizations o ON o.id = p.organization_id WHERE m.user_id = :user_id ORDER BY o.name, p.name"), {"user_id": user.id})).fetchall()
    return {"success": True, "data": [{"id": r[0], "name": r[1], "organization_id": r[2], "organization_name": r[3], "role": r[4]} for r in rows]}


@router.get("/projects/catalog")
async def project_catalog(user: CurrentUser = Depends(get_current_user)):
    """Return projects a signed-in user can request access to."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT p.id, p.name, o.id, o.name FROM projects p JOIN organizations o ON o.id = p.organization_id ORDER BY o.name, p.name"))).fetchall()
    return {"success": True, "data": [{"id": r[0], "name": r[1], "organization_id": r[2], "organization_name": r[3]} for r in rows]}


@router.post("/access-requests", status_code=status.HTTP_201_CREATED)
async def create_access_request(body: AccessRequestCreateIn, user: CurrentUser = Depends(get_current_user)):
    if body.requested_role not in {"viewer", "editor"}:
        raise HTTPException(status_code=422, detail="requested_role must be viewer or editor")
    request_id = new_id()
    async with engine.begin() as conn:
        project = (await conn.execute(text("SELECT organization_id FROM projects WHERE id = :id"), {"id": body.project_id})).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        existing = (await conn.execute(text("SELECT 1 FROM memberships WHERE user_id = :user_id AND project_id = :project_id"), {"user_id": user.id, "project_id": body.project_id})).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="You already have access to this project")
        pending = (await conn.execute(text("SELECT 1 FROM access_requests WHERE user_id = :user_id AND project_id = :project_id AND status = 'pending'"), {"user_id": user.id, "project_id": body.project_id})).fetchone()
        if pending:
            raise HTTPException(status_code=409, detail="An access request is already pending")
        await conn.execute(text(
            "INSERT INTO access_requests "
            "(id, user_id, organization_id, project_id, requested_role, "
            "reason, status, created_at) "
            "VALUES (:id, :user_id, :organization_id, :project_id, "
            ":requested_role, :reason, 'pending', NOW())"
        ), {"id": request_id, "user_id": user.id, "organization_id": project[0], "project_id": body.project_id, "requested_role": body.requested_role, "reason": body.reason})
        await audit(conn, action="access_request.created", actor_user_id=user.id, resource_type="access_request", resource_id=request_id, organization_id=project[0], project_id=body.project_id, details={"requested_role": body.requested_role})
    return {"success": True, "data": {"id": request_id, "status": "pending"}}


@router.get("/access-requests/mine")
async def list_my_access_requests(user: CurrentUser = Depends(get_current_user)):
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT ar.id, ar.project_id, p.name, ar.requested_role, ar.status, ar.reason, ar.created_at, ar.reviewed_at FROM access_requests ar JOIN projects p ON p.id = ar.project_id WHERE ar.user_id = :user_id ORDER BY ar.created_at DESC"), {"user_id": user.id})).fetchall()
    return {"success": True, "data": [{"id": r[0], "project_id": r[1], "project_name": r[2], "requested_role": r[3], "status": r[4], "reason": r[5], "created_at": r[6].isoformat(), "reviewed_at": r[7].isoformat() if r[7] else None} for r in rows]}


@router.get("/admin/access-requests")
async def list_access_requests(user: CurrentUser = Depends(require_platform_admin)):
    async with engine.connect() as conn:
        _sql = (
            "SELECT ar.id, u.email, u.display_name, ar.project_id, p.name, "
            "ar.requested_role, ar.reason, ar.status, ar.created_at "
            "FROM access_requests ar "
            "JOIN users u ON u.id = ar.user_id "
            "JOIN projects p ON p.id = ar.project_id "
            "WHERE ar.status = 'pending' ORDER BY ar.created_at"
        )
        rows = (await conn.execute(text(_sql))).fetchall()
    return {"success": True, "data": [{"id": r[0], "email": r[1], "display_name": r[2], "project_id": r[3], "project_name": r[4], "requested_role": r[5], "reason": r[6], "status": r[7], "created_at": r[8].isoformat()} for r in rows]}


@router.post("/admin/access-requests/{request_id}/review")
async def review_access_request(request_id: str, body: AccessRequestReviewIn, user: CurrentUser = Depends(require_platform_admin)):
    if body.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="decision must be approved or rejected")
    async with engine.begin() as conn:
        request = (await conn.execute(text("SELECT user_id, organization_id, project_id, requested_role, status FROM access_requests WHERE id = :id FOR UPDATE"), {"id": request_id})).fetchone()
        if request is None:
            raise HTTPException(status_code=404, detail="Access request not found")
        if request[4] != "pending":
            raise HTTPException(status_code=409, detail="Access request has already been reviewed")
        await conn.execute(text("UPDATE access_requests SET status = :decision, reviewer_id = :reviewer_id, review_note = :review_note, reviewed_at = NOW() WHERE id = :id"), {"decision": body.decision, "reviewer_id": user.id, "review_note": body.review_note, "id": request_id})
        if body.decision == "approved":
            await conn.execute(text("INSERT INTO memberships (id, user_id, organization_id, project_id, role, created_at) VALUES (:id, :user_id, :organization_id, :project_id, :role, NOW())"), {"id": new_id(), "user_id": request[0], "organization_id": request[1], "project_id": request[2], "role": request[3]})
        await audit(conn, action=f"access_request.{body.decision}", actor_user_id=user.id, resource_type="access_request", resource_id=request_id, organization_id=request[1], project_id=request[2], details={"requested_role": request[3], "review_note": body.review_note})
    return {"success": True, "data": {"id": request_id, "status": body.decision}}


@router.get("/audit-logs")
async def list_audit_logs(
    project_id: str | None = None,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    if project_id and not user.is_platform_admin:
        await require_project_role(project_id, user, {"viewer", "editor"})
    if not project_id and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Select a project to view its audit log")
    where = "WHERE project_id = :project_id" if project_id else ""
    params = {"limit": limit}
    if project_id:
        params["project_id"] = project_id
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, actor_user_id, organization_id, project_id, action, resource_type, resource_id, details, created_at FROM audit_logs " + where + " ORDER BY created_at DESC LIMIT :limit"), params)).fetchall()  # nosec B608
    return {"success": True, "data": [{"id": row[0], "actor_user_id": row[1], "organization_id": row[2], "project_id": row[3], "action": row[4], "resource_type": row[5], "resource_id": row[6], "details": row[7], "created_at": row[8].isoformat()} for row in rows]}
