"""Change title to nullable

Revision ID: 8696c8476be3
Revises: fe72a4a557a0
Create Date: 2021-05-13 15:37:08.810492

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8696c8476be3'
down_revision = 'fe72a4a557a0'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('c_content', 'title', existing_type=sa.VARCHAR(length=10000), nullable=True)


def downgrade():
    op.alter_column('c_content', 'title', existing_type=sa.VARCHAR(length=10000), nullable=False)
