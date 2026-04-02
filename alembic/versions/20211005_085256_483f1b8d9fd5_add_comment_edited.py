"""Add comment edited

Revision ID: 483f1b8d9fd5
Revises: ef7bbb688cac
Create Date: 2021-10-05 08:52:56.957008

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '483f1b8d9fd5'
down_revision = 'ef7bbb688cac'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_comment', sa.Column('edited', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('c_comment', 'edited')
