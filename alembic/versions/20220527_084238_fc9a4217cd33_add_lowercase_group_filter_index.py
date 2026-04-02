"""Add lowercase group filter index

Revision ID: fc9a4217cd33
Revises: bcd1471337bf
Create Date: 2022-05-27 08:42:38.319911

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fc9a4217cd33'
down_revision = 'bcd1471337bf'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE INDEX ix_g_group_member_filter_user_email_lower ON g_group_member_filter (lower(user_email))')


def downgrade():
    op.drop_index(op.f('ix_g_group_member_filter_user_email_lower'), table_name='g_group_member_filter')
