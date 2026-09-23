"""Voeg starttijd toe aan club_evenings (voor een accurate inschrijftermijn)

Revision ID: 016
Revises: 015
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('club_evenings', sa.Column('starttijd', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('club_evenings', 'starttijd')
