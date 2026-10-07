"""add devices.is_shared

Shared devices are visible (read-only) to every signed-in user.

Revision ID: b3e7a1d5c920
Revises: 9c2d4f1a8e37
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e7a1d5c920'
down_revision: Union[str, Sequence[str], None] = '9c2d4f1a8e37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devices', sa.Column('is_shared', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('devices', 'is_shared')
