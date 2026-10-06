"""add recurring_manual_pairs table

Revision ID: 018
Revises: 017
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('recurring_manual_pairs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(), nullable=False),
    sa.Column('naam_1', sa.String(), nullable=False),
    sa.Column('naam_2', sa.String(), nullable=True),
    sa.Column('lidnummer_1', sa.String(), nullable=True),
    sa.Column('lidnummer_2', sa.String(), nullable=True),
    sa.Column('interval', sa.Integer(), nullable=False),
    sa.Column('herhaal_tot', sa.Date(), nullable=True),
    sa.Column('actief', sa.Boolean(), nullable=False),
    sa.Column('referentie_datum', sa.Date(), nullable=False),
    sa.Column('club_id', sa.Integer(), nullable=True),
    sa.Column('aangemaakt_op', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recurring_manual_pairs_id'), 'recurring_manual_pairs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_recurring_manual_pairs_id'), table_name='recurring_manual_pairs')
    op.drop_table('recurring_manual_pairs')
