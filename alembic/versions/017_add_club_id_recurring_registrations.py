"""Voeg club_id toe aan recurring_registrations zodat een herhaalaanmelding
alleen geldt voor avonden van de club waarvoor ze is aangemaakt

Revision ID: 017
Revises: 016
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recurring_registrations', sa.Column('club_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('recurring_registrations', 'club_id')
