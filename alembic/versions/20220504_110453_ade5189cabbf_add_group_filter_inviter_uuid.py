"""Add group filter inviter_uuid

Revision ID: ade5189cabbf
Revises: 72c002cd51af
Create Date: 2022-05-04 11:04:53.839306

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ade5189cabbf'
down_revision = '72c002cd51af'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('g_group_member_filter', sa.Column('inviter_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(op.f('fk_g_group_member_filter_inviter_uuid_u_user'), 'g_group_member_filter', 'u_user', ['inviter_uuid'], ['user_uuid'])


def downgrade():
    op.drop_constraint(op.f('fk_g_group_member_filter_inviter_uuid_u_user'), 'g_group_member_filter', type_='foreignkey')
    op.drop_column('g_group_member_filter', 'inviter_uuid')
