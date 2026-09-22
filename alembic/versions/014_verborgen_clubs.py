"""Voeg members.verborgen_clubs toe (zichtbaarheid van clubs op de agenda)

Revision ID: 014
Revises: 013
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('members') as batch_op:
        batch_op.add_column(sa.Column('verborgen_clubs', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('members') as batch_op:
        batch_op.drop_column('verborgen_clubs')
