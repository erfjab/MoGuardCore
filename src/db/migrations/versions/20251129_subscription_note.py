"""subscription note

Revision ID: 4d3e6b790f6a
Revises: 3c2f5a589e5f
Create Date: 2025-11-29 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d3e6b790f6a"
down_revision: Union[str, Sequence[str], None] = "3c2f5a589e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("subscriptions", sa.Column("note", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("subscriptions", "note")
