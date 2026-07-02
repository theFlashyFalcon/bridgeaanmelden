"""Voeg is_systeem toe aan berichten om automatische notificaties te onderscheiden

Revision ID: 011
Revises: 010
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.add_column(sa.Column('is_systeem', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.drop_column('is_systeem')
