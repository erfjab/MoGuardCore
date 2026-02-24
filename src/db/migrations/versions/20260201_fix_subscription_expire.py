"""fix subscription expire

Revision ID: 123456abcdef
Revises: ba54ac57f9ce
Create Date: 2026-02-01 13:30:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = "123456abcdef"
down_revision: Union[str, Sequence[str], None] = "ba54ac57f9ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    now_ts = int(datetime.utcnow().timestamp())
    max_seconds = 315360000  # 10 years
    max_ts = now_ts + max_seconds
    min_duration = -max_seconds
    op.execute(sa.text(f"UPDATE subscriptions SET limit_expire = {max_ts} WHERE limit_expire > {max_ts} AND limit_expire > 0"))
    op.execute(
        sa.text(
            f"UPDATE subscriptions SET limit_expire = {min_duration} WHERE limit_expire < {min_duration} AND limit_expire < 0"
        )
    )


def downgrade() -> None:
    pass
