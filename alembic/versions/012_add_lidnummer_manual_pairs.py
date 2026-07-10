"""Voeg optionele lidnummer-velden toe aan manual_pairs

Revision ID: 012
Revises: 011
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.add_column(sa.Column('lidnummer_1', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('lidnummer_2', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('lidnummer_3', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('lidnummer_4', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('lidnummer_5', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('lidnummer_6', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('manual_pairs') as batch_op:
        batch_op.drop_column('lidnummer_1')
        batch_op.drop_column('lidnummer_2')
        batch_op.drop_column('lidnummer_3')
        batch_op.drop_column('lidnummer_4')
        batch_op.drop_column('lidnummer_5')
        batch_op.drop_column('lidnummer_6')
