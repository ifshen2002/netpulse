"""merge probes and links into endpoints — single source of truth

Revision ID: 013
Revises: 012
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add runtime columns to endpoints
    op.add_column("endpoints", sa.Column("status", sa.String(), nullable=False, server_default="gray"))
    op.add_column("endpoints", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("endpoints", sa.Column("protocol", sa.String(), nullable=False, server_default="icmp"))

    # Backfill runtime data from probes
    op.execute(
        sa.text(
            "UPDATE endpoints e SET "
            "status = p.status, last_seen = p.last_seen, protocol = p.protocol "
            "FROM probes p WHERE p.endpoint_id = e.id"
        )
    )

    # 2. Add endpoint_id to child tables
    for table in ("packet_evidence", "probe_metrics", "alerts", "incidents"):
        op.add_column(table, sa.Column("endpoint_id", sa.String(), nullable=True))

    # 3. Backfill endpoint_id via probe join
    op.execute(
        sa.text(
            "UPDATE packet_evidence pe SET endpoint_id = p.endpoint_id "
            "FROM probes p WHERE p.id = pe.probe_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE probe_metrics pm SET endpoint_id = p.endpoint_id "
            "FROM probes p WHERE p.id = pm.probe_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE alerts a SET endpoint_id = p.endpoint_id "
            "FROM probes p WHERE p.id = a.probe_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE incidents i SET endpoint_id = p.endpoint_id "
            "FROM probes p WHERE p.id = i.probe_id"
        )
    )

    # 4. Drop old probe_id / link_id columns (CASCADE drops FKs too)
    op.execute(sa.text("ALTER TABLE packet_evidence DROP COLUMN probe_id CASCADE"))
    op.execute(sa.text("ALTER TABLE packet_evidence DROP COLUMN link_id CASCADE"))
    op.execute(sa.text("ALTER TABLE probe_metrics DROP COLUMN probe_id CASCADE"))
    op.execute(sa.text("ALTER TABLE probe_metrics DROP COLUMN link_id CASCADE"))
    op.execute(sa.text("ALTER TABLE alerts DROP COLUMN probe_id CASCADE"))
    op.execute(sa.text("ALTER TABLE incidents DROP COLUMN probe_id CASCADE"))

    # 5. Set endpoint_id NOT NULL on data tables
    for table in ("packet_evidence", "probe_metrics"):
        op.alter_column(table, "endpoint_id", nullable=False)

    # 6. Add FK constraints to endpoints
    for table in ("packet_evidence", "probe_metrics", "alerts", "incidents"):
        op.create_foreign_key(
            f"fk_{table}_endpoint_id", table, "endpoints", ["endpoint_id"], ["id"]
        )

    # 7. Create indexes on endpoint_id
    for table in ("packet_evidence", "probe_metrics"):
        op.create_index(f"ix_{table}_endpoint_timestamp", table, ["endpoint_id", "timestamp"])

    # 8. Drop links and probes tables
    op.drop_table("links")
    op.drop_table("probes")


def downgrade() -> None:
    # Not reversible — recreating probes/links would lose the merged data model.
    # This is a one-way consolidation migration.
    pass
