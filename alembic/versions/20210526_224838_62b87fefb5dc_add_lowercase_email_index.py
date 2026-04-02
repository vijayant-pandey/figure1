"""Add lowercase email index

Revision ID: 62b87fefb5dc
Revises: 9c3965bcccdd
Create Date: 2021-05-26 22:48:38.928311

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '62b87fefb5dc'
down_revision = '9c3965bcccdd'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE UNIQUE INDEX ix_u_user_email_lower ON u_user (lower(email))')


def downgrade():
    op.drop_index(op.f('ix_u_user_email_lower'), table_name='u_user')
