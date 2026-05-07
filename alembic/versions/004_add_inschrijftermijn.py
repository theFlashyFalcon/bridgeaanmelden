"""add inschrijftermijn_uren to club_evenings and te_laat to registrations

Revision ID: 004
Revises: 003
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('club_evenings',
        sa.Column('inschrijftermijn_uren', sa.Integer(), nullable=True))
    op.add_column('registrations',
        sa.Column('te_laat', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('registrations',
        sa.Column('te_laat_goedgekeurd', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('registrations', 'te_laat_goedgekeurd')
    op.drop_column('registrations', 'te_laat')
    op.drop_column('club_evenings', 'inschrijftermijn_uren')
