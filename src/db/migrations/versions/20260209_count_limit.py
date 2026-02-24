"""count limit

Revision ID: 2c273eaf377c
Revises: f30bfb8700ae
Create Date: 2026-02-09 06:38:51.280876

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c273eaf377c"
down_revision: Union[str, Sequence[str], None] = "f30bfb8700ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Set count_limit for all admins:
    - Admins with current_count <= 300: set to 300
    - Admins with 300 < current_count <= 400: set to 400
    - Admins with 400 < current_count <= 500: set to 500
    - Continue pattern in increments of 100
    """
    conn = op.get_bind()

    # Get all admins with their current counts
    result = conn.execute(
        sa.text("""
        SELECT id, current_count, count_limit 
        FROM admins 
        WHERE removed = false
    """)
    )

    admins = result.fetchall()

    for admin in admins:
        admin_id, current_count, existing_limit = admin

        # Calculate new limit based on current count
        if current_count <= 300:
            new_limit = 300
        else:
            # Round up to next hundred
            new_limit = ((current_count // 100) + 1) * 100

        # Update the admin's count_limit
        conn.execute(
            sa.text("""
            UPDATE admins 
            SET count_limit = :new_limit 
            WHERE id = :admin_id
        """),
            {"new_limit": new_limit, "admin_id": admin_id},
        )

        print(f"Admin ID {admin_id}: current_count={current_count}, old_limit={existing_limit}, new_limit={new_limit}")


def downgrade() -> None:
    """
    Revert count_limit changes - set back to NULL for flexibility
    """
    conn = op.get_bind()
    conn.execute(
        sa.text("""
        UPDATE admins 
        SET count_limit = NULL 
        WHERE removed = false
    """)
    )
