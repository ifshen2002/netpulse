"""add source_ip column to endpoints

Revision ID: 012
Revises: 011
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("source_ip", sa.String(), nullable=True))

    # Backfill existing endpoints from packet_evidence src_ip.
    op.execute(
        sa.text(
            "UPDATE endpoints e SET source_ip = pe.src_ip "
            "FROM ("
            "  SELECT DISTINCT ON (p.endpoint_id) p.endpoint_id, pe2.src_ip "
            "  FROM probes p "
            "  JOIN packet_evidence pe2 ON pe2.probe_id = p.id "
            "  ORDER BY p.endpoint_id, pe2.timestamp DESC"
            ") pe WHERE pe.endpoint_id = e.id AND e.source_ip IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("endpoints", "source_ip")
