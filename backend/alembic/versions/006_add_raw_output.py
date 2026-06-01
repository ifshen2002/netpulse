"""add raw_output column to packet_evidence

Revision ID: 006
Revises: 005
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("packet_evidence", sa.Column("raw_output", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("packet_evidence", "raw_output")
