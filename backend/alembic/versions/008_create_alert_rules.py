"""create alert_rules table

Revision ID: 008
Revises: 007
Create Date: 2026-06-01
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="critical"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    now = datetime.now(timezone.utc)

    rules_table = table(
        "alert_rules",
        column("id"), column("name"), column("metric"),
        column("operator"), column("threshold"),
        column("severity"), column("enabled"), column("created_at"),
    )
    op.bulk_insert(
        rules_table,
        [
            {"id": "rule-latency-warn", "name": "Latency Warning", "metric": "latency",
             "operator": ">", "threshold": 200.0, "severity": "warning", "enabled": True, "created_at": now},
            {"id": "rule-latency-crit", "name": "Latency Critical", "metric": "latency",
             "operator": ">", "threshold": 300.0, "severity": "critical", "enabled": True, "created_at": now},
            {"id": "rule-loss-warn", "name": "Packet Loss Warning", "metric": "packet_loss",
             "operator": ">=", "threshold": 3.0, "severity": "warning", "enabled": True, "created_at": now},
            {"id": "rule-loss-crit", "name": "Packet Loss Critical", "metric": "packet_loss",
             "operator": ">=", "threshold": 5.0, "severity": "critical", "enabled": True, "created_at": now},
            {"id": "rule-avail-crit", "name": "Availability Low", "metric": "availability",
             "operator": "<=", "threshold": 95.0, "severity": "critical", "enabled": True, "created_at": now},
        ],
    )


def downgrade() -> None:
    op.drop_table("alert_rules")
