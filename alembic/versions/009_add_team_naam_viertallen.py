"""Voeg team_naam toe aan registrations en extra naam-velden aan manual_pairs voor viertallen

Revision ID: 009
Revises: 008
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('registrations') as batch_op:
        batch_op.add_column(sa.Column('team_naam', sa.String(), nullable=True))
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.add_column(sa.Column('naam_3', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('naam_4', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('team_naam', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('registrations') as batch_op:
        batch_op.drop_column('team_naam')
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.drop_column('naam_3')
        batch_op.drop_column('naam_4')
        batch_op.drop_column('team_naam')
