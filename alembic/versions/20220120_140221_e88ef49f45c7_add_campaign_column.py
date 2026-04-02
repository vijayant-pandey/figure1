""" add campign column

Revision ID: e88ef49f45c7
Revises: ec508fff0093
Create Date: 2022-01-20 14:02:21.412248

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e88ef49f45c7'
down_revision = 'ec508fff0093'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_campaign', sa.Column('is_sponsored', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('c_campaign', 'is_sponsored')

