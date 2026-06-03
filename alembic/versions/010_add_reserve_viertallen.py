"""Voeg reserve-spelers toe aan registrations en manual_pairs voor viertallen

Revision ID: 010
Revises: 009
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('registrations') as batch_op:
        batch_op.add_column(sa.Column('reserve1_naam', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('reserve2_naam', sa.String(), nullable=True))
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.add_column(sa.Column('naam_5', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('naam_6', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('registrations') as batch_op:
        batch_op.drop_column('reserve1_naam')
        batch_op.drop_column('reserve2_naam')
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.drop_column('naam_5')
        batch_op.drop_column('naam_6')
