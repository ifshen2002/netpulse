"""extend alerts and incidents for probe support

Revision ID: 005
Revises: 004
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("alerts", "node_id", existing_type=sa.String(), nullable=True)

    op.add_column("alerts", sa.Column("probe_id", sa.String(), sa.ForeignKey("probes.id"), nullable=True))
    op.add_column("incidents", sa.Column("probe_id", sa.String(), sa.ForeignKey("probes.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "probe_id")
    op.drop_column("alerts", "probe_id")
    op.alter_column("alerts", "node_id", existing_type=sa.String(), nullable=False)
