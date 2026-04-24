"""add naam to club_evenings and wachtwoord_hash to account_requests

Revision ID: 001
Revises:
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("club_evenings") as batch_op:
        batch_op.add_column(sa.Column("naam", sa.String(), nullable=True))

    with op.batch_alter_table("account_requests") as batch_op:
        batch_op.add_column(sa.Column("wachtwoord_hash", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("club_evenings") as batch_op:
        batch_op.drop_column("naam")

    with op.batch_alter_table("account_requests") as batch_op:
        batch_op.drop_column("wachtwoord_hash")
