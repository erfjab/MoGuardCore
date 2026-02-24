"""add telegram logger fields to admins and subscriptions

Revision ID: 20251202_telegram_logger
Revises: 3c8f4a2b1e9d
Create Date: 2025-12-02

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251202_telegram_logger"
down_revision = "3c8f4a2b1e9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add telegram logger fields to admins
    op.add_column("admins", sa.Column("telegram_logger_id", sa.String(64), nullable=True))
    op.add_column("admins", sa.Column("telegram_topic_id", sa.String(64), nullable=True))
    op.add_column("admins", sa.Column("telegram_status", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("admins", sa.Column("telegram_send_subscriptions", sa.Boolean(), nullable=True, server_default="false"))
    op.execute(
        "UPDATE admins SET telegram_status = false, telegram_send_subscriptions = false, telegram_logger_id = telegram_id, telegram_topic_id = NULL"
    )

    # Add telegram_id to subscriptions
    op.add_column("subscriptions", sa.Column("telegram_id", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("admins", "telegram_logger_id")
    op.drop_column("admins", "telegram_topic_id")
    op.drop_column("admins", "telegram_status")
    op.drop_column("admins", "telegram_send_subscriptions")
    op.drop_column("subscriptions", "telegram_id")
