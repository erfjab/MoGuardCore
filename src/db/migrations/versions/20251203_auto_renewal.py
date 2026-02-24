"""add subscription_auto_renewals table

Revision ID: 20251203_auto_renewal
Revises: 20251203_auto_delete_days
Create Date: 2025-12-03

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251203_auto_renewal"
down_revision = "20251203_auto_delete_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_auto_renewals",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False, index=True),
        sa.Column("limit_expire", sa.BigInteger(), nullable=True, default=0),
        sa.Column("limit_usage", sa.BigInteger(), nullable=True, default=0),
        sa.Column("reset_usage", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("subscription_auto_renewals")
