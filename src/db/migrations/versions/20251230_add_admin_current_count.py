"""add admin current count

Revision ID: c1d2e3f4g5h6
Revises: baab11b1894a
Create Date: 2025-12-30 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, Sequence[str], None] = "baab11b1894a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("admins", sa.Column("current_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        "UPDATE admins SET current_count = (SELECT COUNT(*) FROM subscriptions WHERE subscriptions.owner_id = admins.id AND subscriptions.removed = FALSE)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("admins", "current_count")
