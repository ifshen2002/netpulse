"""create probes, links, probe_metrics, and packet_evidence tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-31
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "probes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("protocol", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="gray"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("probe_id", sa.String(), sa.ForeignKey("probes.id"), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("protocol", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="gray"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "packet_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("probe_id", sa.String(), sa.ForeignKey("probes.id"), nullable=False),
        sa.Column("link_id", sa.String(), sa.ForeignKey("links.id"), nullable=False),
        sa.Column("protocol", sa.String(), nullable=False),
        sa.Column("src_ip", sa.String(), nullable=False),
        sa.Column("dst_ip", sa.String(), nullable=False),
        sa.Column("ttl", sa.Integer(), nullable=False),
        sa.Column("packet_size_bytes", sa.Integer(), nullable=False),
        sa.Column("icmp_seq", sa.Integer(), nullable=False),
        sa.Column("rtt_ms", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "probe_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("probe_id", sa.String(), sa.ForeignKey("probes.id"), nullable=False),
        sa.Column("link_id", sa.String(), sa.ForeignKey("links.id"), nullable=False),
        sa.Column("packet_evidence_id", sa.String(), sa.ForeignKey("packet_evidence.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("packet_loss_pct", sa.Float(), nullable=False),
        sa.Column("availability_pct", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_probe_metrics_probe_timestamp", "probe_metrics", ["probe_id", "timestamp"])
    op.create_index("ix_probe_metrics_link_timestamp", "probe_metrics", ["link_id", "timestamp"])

    now = datetime.now(timezone.utc)

    probes_table = table(
        "probes",
        column("id"), column("name"), column("protocol"), column("endpoint"),
        column("status"), column("last_seen"), column("created_at"),
    )
    op.bulk_insert(
        probes_table,
        [
            {"id": "probe-a", "name": "Google DNS", "protocol": "icmp", "endpoint": "8.8.8.8",
             "status": "gray", "last_seen": now, "created_at": now},
            {"id": "probe-b", "name": "Cloudflare DNS", "protocol": "icmp", "endpoint": "1.1.1.1",
             "status": "gray", "last_seen": now, "created_at": now},
            {"id": "probe-c", "name": "Quad9 DNS", "protocol": "icmp", "endpoint": "9.9.9.9",
             "status": "gray", "last_seen": now, "created_at": now},
        ],
    )

    links_table = table(
        "links",
        column("id"), column("probe_id"), column("endpoint"), column("protocol"),
        column("status"), column("last_seen"), column("created_at"),
    )
    op.bulk_insert(
        links_table,
        [
            {"id": "link-a", "probe_id": "probe-a", "endpoint": "8.8.8.8", "protocol": "icmp",
             "status": "gray", "last_seen": now, "created_at": now},
            {"id": "link-b", "probe_id": "probe-b", "endpoint": "1.1.1.1", "protocol": "icmp",
             "status": "gray", "last_seen": now, "created_at": now},
            {"id": "link-c", "probe_id": "probe-c", "endpoint": "9.9.9.9", "protocol": "icmp",
             "status": "gray", "last_seen": now, "created_at": now},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_probe_metrics_link_timestamp", table_name="probe_metrics")
    op.drop_index("ix_probe_metrics_probe_timestamp", table_name="probe_metrics")
    op.drop_table("packet_evidence")
    op.drop_table("probe_metrics")
    op.drop_table("links")
    op.drop_table("probes")
