"""20251230_cache_total_usage_and_online_at

Revision ID: baab11b1894a
Revises: 63ad0e5bcd75
Create Date: 2025-12-30 01:16:39.917773

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "baab11b1894a"
down_revision: Union[str, Sequence[str], None] = "63ad0e5bcd75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add cached columns for total_usage and online_at
    op.add_column("subscriptions", sa.Column("total_usage", sa.BigInteger(), nullable=True))
    op.add_column("subscriptions", sa.Column("online_at", sa.DateTime(), nullable=True))

    # Initialize with current values from subscription_usages
    op.execute("""
        UPDATE subscriptions
        SET total_usage = COALESCE((
            SELECT SUM(usage) 
            FROM subscription_usages 
            WHERE subscription_usages.subscription_id = subscriptions.id
        ), 0)
    """)

    op.execute("""
        UPDATE subscriptions
        SET online_at = (
            SELECT MAX(updated_at) 
            FROM subscription_usages 
            WHERE subscription_usages.subscription_id = subscriptions.id
        )
    """)

    # Make total_usage NOT NULL with default 0
    op.alter_column("subscriptions", "total_usage", nullable=False, server_default="0")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subscriptions", "online_at")
    op.drop_column("subscriptions", "total_usage")
