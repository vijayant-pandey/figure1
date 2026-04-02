"""Add feature for public notifications

Revision ID: ec508fff0093
Revises: 5d4092dc5525
Create Date: 2022-01-17 12:49:31.882383

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ec508fff0093'
down_revision = '5d4092dc5525'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_features', sa.Column('public_notifications_enabled', sa.Boolean(), nullable=True))
    op.execute("UPDATE c_features SET public_notifications_enabled=True")
    op.alter_column('c_features', 'public_notifications_enabled', nullable=False)


def downgrade():
    op.drop_column('c_features', 'public_notifications_enabled')
