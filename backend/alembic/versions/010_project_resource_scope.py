"""Add project ownership to monitoring resources and backfill legacy data."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESOURCE_TABLES = (
    "nodes", "metrics", "alerts", "incidents", "chaos_events",
    "endpoints", "probes", "links", "probe_metrics", "alert_rules", "packet_evidence",
)


def upgrade() -> None:
    for table in RESOURCE_TABLES:
        op.add_column(table, sa.Column("project_id", sa.String(), nullable=True))
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
        op.create_foreign_key(f"fk_{table}_project_id", table, "projects", ["project_id"], ["id"])

    # Existing demo/self-observation data belongs to the first bootstrap project.
    for table in RESOURCE_TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET project_id = (SELECT id FROM projects ORDER BY created_at LIMIT 1) "
                "WHERE project_id IS NULL"
            )
        )


def downgrade() -> None:
    for table in reversed(RESOURCE_TABLES):
        op.drop_constraint(f"fk_{table}_project_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_project_id", table_name=table)
        op.drop_column(table, "project_id")
