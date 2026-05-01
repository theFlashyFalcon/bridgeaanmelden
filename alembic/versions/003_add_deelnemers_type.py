"""add deelnemers_type to club_evenings and partner2/3 to registrations

Revision ID: 003
Revises: 67f0cd9fa494
Create Date: 2026-05-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003'
down_revision: Union[str, None] = '67f0cd9fa494'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('club_evenings',
        sa.Column('deelnemers_type', sa.String(), nullable=False, server_default='paren'))
    op.add_column('registrations',
        sa.Column('partner2_naam', sa.String(), nullable=True))
    op.add_column('registrations',
        sa.Column('partner3_naam', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('registrations', 'partner3_naam')
    op.drop_column('registrations', 'partner2_naam')
    op.drop_column('club_evenings', 'deelnemers_type')
