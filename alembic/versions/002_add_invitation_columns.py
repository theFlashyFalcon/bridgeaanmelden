"""add account_request_id and member_id to invitations if missing

Revision ID: 002
Revises: 001
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})"))]
    return column in cols


def upgrade() -> None:
    with op.batch_alter_table("invitations") as batch_op:
        if not _column_exists("invitations", "member_id"):
            batch_op.add_column(sa.Column("member_id", sa.Integer(), nullable=True))
        if not _column_exists("invitations", "account_request_id"):
            batch_op.add_column(sa.Column("account_request_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invitations") as batch_op:
        batch_op.drop_column("account_request_id")
        batch_op.drop_column("member_id")
