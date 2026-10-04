"""add device region and recording species filter

devices.region_code: province/district (ISO 3166-2:LK) for BirdNET's
location filter. recordings.species_filter: which filter produced a
recording's detections.

Revision ID: 9c2d4f1a8e37
Revises: 7a1c3e9b2f40
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c2d4f1a8e37'
down_revision: Union[str, Sequence[str], None] = '7a1c3e9b2f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devices', sa.Column('region_code', sa.String(length=8), nullable=True))
    op.add_column('recordings', sa.Column('species_filter', sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('recordings', 'species_filter')
    op.drop_column('devices', 'region_code')
