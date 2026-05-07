"""Voeg is_nieuws toe aan berichten en maak ontvanger_id nullable

Revision ID: 005
Revises: 004
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('berichten',
        sa.Column('is_nieuws', sa.Boolean(), nullable=False, server_default='0'))
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.alter_column('ontvanger_id', nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('berichten') as batch_op:
        batch_op.alter_column('ontvanger_id', nullable=False)
    op.drop_column('berichten', 'is_nieuws')
