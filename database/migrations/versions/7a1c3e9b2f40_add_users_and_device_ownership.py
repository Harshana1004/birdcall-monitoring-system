"""add users and device ownership

Adds the users table, one owner (plus a hashed claim code) per
device, and the uploading user for manual-analysis recordings.

Revision ID: 7a1c3e9b2f40
Revises: 6d6e486a2134
Create Date: 2026-10-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7a1c3e9b2f40'
down_revision: Union[str, Sequence[str], None] = '6d6e486a2134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=True),
        sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    )

    op.add_column('devices', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('devices', sa.Column('claim_code_hash', sa.String(length=255), nullable=True))
    op.add_column('devices', sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_devices_owner_id_users'), 'devices', 'users',
        ['owner_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_devices_owner_id', 'devices', ['owner_id'], unique=False)

    op.add_column('recordings', sa.Column('uploaded_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_recordings_uploaded_by_user_id_users'), 'recordings', 'users',
        ['uploaded_by_user_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_recordings_uploaded_by_user_id', 'recordings', ['uploaded_by_user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_recordings_uploaded_by_user_id', table_name='recordings')
    op.drop_constraint(op.f('fk_recordings_uploaded_by_user_id_users'), 'recordings', type_='foreignkey')
    op.drop_column('recordings', 'uploaded_by_user_id')

    op.drop_index('ix_devices_owner_id', table_name='devices')
    op.drop_constraint(op.f('fk_devices_owner_id_users'), 'devices', type_='foreignkey')
    op.drop_column('devices', 'claimed_at')
    op.drop_column('devices', 'claim_code_hash')
    op.drop_column('devices', 'owner_id')

    op.drop_table('users')
