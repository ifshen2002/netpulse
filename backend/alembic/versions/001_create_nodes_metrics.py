"""create nodes and metrics tables

Revision ID: 001
Revises: None
Create Date: 2026-05-16
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="green"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_id", sa.String(), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu", sa.Float(), nullable=False),
        sa.Column("memory", sa.Float(), nullable=False),
        sa.Column("disk", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("packet_loss_pct", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metrics_node_timestamp", "metrics", ["node_id", "timestamp"])

    now = datetime.now(timezone.utc)
    nodes_table = table("nodes", column("id"), column("name"), column("type"), column("status"), column("last_seen"), column("created_at"))
    op.bulk_insert(
        nodes_table,
        [
            {"id": "node-1", "name": "Host Observer", "type": "real", "status": "green", "last_seen": now, "created_at": now},
            {"id": "node-2", "name": "Cloud Service A", "type": "synthetic", "status": "green", "last_seen": now, "created_at": now},
            {"id": "node-3", "name": "Cloud Service B", "type": "synthetic", "status": "green", "last_seen": now, "created_at": now},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_metrics_node_timestamp", table_name="metrics")
    op.drop_table("metrics")
    op.drop_table("nodes")
