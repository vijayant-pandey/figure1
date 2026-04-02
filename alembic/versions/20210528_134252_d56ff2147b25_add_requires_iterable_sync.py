"""Add requires_iterable_sync

Revision ID: d56ff2147b25
Revises: 62b87fefb5dc
Create Date: 2021-05-28 13:42:52.307156

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd56ff2147b25'
down_revision = '62b87fefb5dc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('u_user_state', sa.Column('requires_iterable_sync', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('u_user_state', 'requires_iterable_sync')
