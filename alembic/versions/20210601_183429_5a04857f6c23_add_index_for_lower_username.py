"""Add index for lower(username)

Revision ID: 5a04857f6c23
Revises: a2d65d4e4ad5
Create Date: 2021-06-01 18:34:29.283715

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5a04857f6c23'
down_revision = 'a2d65d4e4ad5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE INDEX ix_u_user_username_lower ON u_user (lower(username))')


def downgrade():
    op.drop_index(op.f('ix_u_user_username_lower'), table_name='u_user')
