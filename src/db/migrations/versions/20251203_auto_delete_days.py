"""add auto_delete_days to subscriptions

Revision ID: 20251203_auto_delete_days
Revises: 20251202_telegram_logger
Create Date: 2025-12-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251203_auto_delete_days"
down_revision = "20251202_telegram_logger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("auto_delete_days", sa.Integer(), nullable=True, server_default="0"))
    op.execute("UPDATE subscriptions SET auto_delete_days = 0")


def downgrade() -> None:
    op.drop_column("subscriptions", "auto_delete_days")
