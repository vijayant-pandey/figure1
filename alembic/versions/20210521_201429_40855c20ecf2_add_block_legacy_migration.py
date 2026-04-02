"""Add block_legacy_migration

Revision ID: 40855c20ecf2
Revises: d7db3857f866
Create Date: 2021-05-21 20:14:29.024009

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '40855c20ecf2'
down_revision = 'd7db3857f866'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('u_user_state', sa.Column('block_legacy_migration', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('u_user_state', 'block_legacy_migration')
