"""Maak tekst nullable in berichten (voor nieuwsberichten zonder berichttekst)

Revision ID: 007
Revises: 006
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.alter_column('tekst', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.alter_column('tekst', existing_type=sa.Text(), nullable=False)
