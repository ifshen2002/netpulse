"""create identity tenancy access-request and audit tables

Revision ID: 009
Revises: 008
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(), primary_key=True), sa.Column("email", sa.String(), nullable=False, unique=True), sa.Column("password_hash", sa.String(), nullable=False), sa.Column("display_name", sa.String(), nullable=False), sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("organizations", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(), nullable=False, unique=True), sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("projects", sa.Column("id", sa.String(), primary_key=True), sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("name", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("organization_id", "name", name="uq_projects_organization_name"))
    op.create_table("memberships", sa.Column("id", sa.String(), primary_key=True), sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False), sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False), sa.Column("role", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("role IN ('viewer', 'editor')", name="ck_memberships_role"), sa.UniqueConstraint("user_id", "project_id", name="uq_memberships_user_project"))
    op.create_table("auth_sessions", sa.Column("id", sa.String(), primary_key=True), sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False), sa.Column("token_hash", sa.String(), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("access_requests", sa.Column("id", sa.String(), primary_key=True), sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False), sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False), sa.Column("requested_role", sa.String(), nullable=False), sa.Column("reason", sa.String(), nullable=True), sa.Column("status", sa.String(), nullable=False), sa.Column("reviewer_id", sa.String(), sa.ForeignKey("users.id"), nullable=True), sa.Column("review_note", sa.String(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True), sa.CheckConstraint("requested_role IN ('viewer', 'editor')", name="ck_access_requests_role"), sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_access_requests_status"))
    op.create_index("uq_access_requests_pending_user_project", "access_requests", ["user_id", "project_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_table("audit_logs", sa.Column("id", sa.String(), primary_key=True), sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True), sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=True), sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=True), sa.Column("action", sa.String(), nullable=False), sa.Column("resource_type", sa.String(), nullable=False), sa.Column("resource_id", sa.String(), nullable=True), sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_logs_project_created", "audit_logs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_project_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("uq_access_requests_pending_user_project", table_name="access_requests")
    op.drop_table("access_requests")
    op.drop_table("auth_sessions")
    op.drop_table("memberships")
    op.drop_table("projects")
    op.drop_table("organizations")
    op.drop_table("users")
