"""create notification subscriptions and in-app notifications tables

Revision ID: 011
Revises: 010
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('warning', 'critical')",
            name="ck_subscriptions_severity",
        ),
        sa.CheckConstraint(
            "resource_type IS NULL OR resource_type IN ('probe', 'endpoint', 'node')",
            name="ck_subscriptions_resource_type",
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "resource_type", "severity",
            name="uq_subscriptions_user_project_type_severity",
        ),
    )

    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("alert_id", sa.String(), sa.ForeignKey("alerts.id"), nullable=True),
        sa.Column("incident_id", sa.String(), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="unread"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_notifications_severity",
        ),
        sa.CheckConstraint(
            "status IN ('unread', 'read', 'acknowledged', 'resolved')",
            name="ck_notifications_status",
        ),
    )
    op.create_index(
        "ix_notifications_user_status_created",
        "in_app_notifications",
        ["user_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_status_created", table_name="in_app_notifications")
    op.drop_table("in_app_notifications")
    op.drop_table("notification_subscriptions")
