"""Voeg aangemaakt_door_id toe aan rankings en uitslagen

Revision ID: 008
Revises: 007
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rankings') as batch_op:
        batch_op.add_column(sa.Column('aangemaakt_door_id', sa.Integer(), sa.ForeignKey('members.id'), nullable=True))
    with op.batch_alter_table('uitslagen') as batch_op:
        batch_op.add_column(sa.Column('aangemaakt_door_id', sa.Integer(), sa.ForeignKey('members.id'), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('rankings') as batch_op:
        batch_op.drop_column('aangemaakt_door_id')
    with op.batch_alter_table('uitslagen') as batch_op:
        batch_op.drop_column('aangemaakt_door_id')
