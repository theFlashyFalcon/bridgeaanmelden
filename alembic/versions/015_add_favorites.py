"""Voeg favorites-tabel toe (favoriete aanmeldpartners)

Revision ID: 015
Revises: 014
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=False),
        sa.Column('voornaam', sa.String(), nullable=False),
        sa.Column('achternaam', sa.String(), nullable=False),
        sa.Column('nbb_nummer', sa.String(), nullable=True),
        sa.Column('aangemaakt_op', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_favorites_member_id', 'favorites', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_favorites_member_id', table_name='favorites')
    op.drop_table('favorites')
