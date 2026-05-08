"""Maak naam_2 nullable in manual_pairs (om solo handmatig toe te voegen)

Revision ID: 006
Revises: 005
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.alter_column('naam_2', nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.alter_column('naam_2', nullable=False)
