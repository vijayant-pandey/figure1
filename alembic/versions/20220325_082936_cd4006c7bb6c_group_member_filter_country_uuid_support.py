"""Group member filter country_uuid support

Revision ID: cd4006c7bb6c
Revises: b43516089106
Create Date: 2022-03-25 08:29:36.985705

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'cd4006c7bb6c'
down_revision = 'b43516089106'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('g_group_member_filter', sa.Column('country_uuid', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('g_group_member_filter', 'country_uuid')
