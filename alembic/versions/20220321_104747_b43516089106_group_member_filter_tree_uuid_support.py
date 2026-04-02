"""Group member filter tree_uuid support

Revision ID: b43516089106
Revises: 71e12a37476d
Create Date: 2022-03-21 10:47:47.129636

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b43516089106'
down_revision = '71e12a37476d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('g_group_member_filter', sa.Column('tree_uuid', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('g_group_member_filter', 'tree_uuid')
