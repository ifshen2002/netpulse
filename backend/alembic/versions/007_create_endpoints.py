"""create endpoints table, add endpoint_id FK to probes

Revision ID: 007
Revises: 006
Create Date: 2026-06-01
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "endpoints",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_host", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("probes", sa.Column("endpoint_id", sa.String(), sa.ForeignKey("endpoints.id"), nullable=True))

    now = datetime.now(timezone.utc)

    endpoints_table = table(
        "endpoints",
        column("id"), column("name"), column("target_host"),
        column("enabled"), column("created_at"),
    )
    op.bulk_insert(
        endpoints_table,
        [
            {"id": "endpoint-a", "name": "Google DNS", "target_host": "8.8.8.8",
             "enabled": True, "created_at": now},
            {"id": "endpoint-b", "name": "Cloudflare DNS", "target_host": "1.1.1.1",
             "enabled": True, "created_at": now},
            {"id": "endpoint-c", "name": "Quad9 DNS", "target_host": "9.9.9.9",
             "enabled": True, "created_at": now},
        ],
    )

    op.execute("UPDATE probes SET endpoint_id = 'endpoint-a' WHERE id = 'probe-a'")
    op.execute("UPDATE probes SET endpoint_id = 'endpoint-b' WHERE id = 'probe-b'")
    op.execute("UPDATE probes SET endpoint_id = 'endpoint-c' WHERE id = 'probe-c'")


def downgrade() -> None:
    op.drop_column("probes", "endpoint_id")
    op.drop_table("endpoints")
