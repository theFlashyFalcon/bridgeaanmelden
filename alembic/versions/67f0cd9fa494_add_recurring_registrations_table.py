"""add recurring_registrations table

Revision ID: 67f0cd9fa494
Revises: 002
Create Date: 2026-04-26 16:17:04.123602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67f0cd9fa494'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('recurring_registrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('member_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('partner_naam', sa.String(), nullable=True),
    sa.Column('interval', sa.Integer(), nullable=False),
    sa.Column('herhaal_tot', sa.Date(), nullable=True),
    sa.Column('actief', sa.Boolean(), nullable=False),
    sa.Column('referentie_datum', sa.Date(), nullable=False),
    sa.Column('aangemaakt_op', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recurring_registrations_id'), 'recurring_registrations', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_recurring_registrations_id'), table_name='recurring_registrations')
    op.drop_table('recurring_registrations')
