"""Change case language to nullable

Revision ID: 6a855a60aaf1
Revises: 5cbfb1fb9590
Create Date: 2021-05-17 16:11:46.365662

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6a855a60aaf1'
down_revision = '5cbfb1fb9590'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('c_case', 'language',
                    existing_type=sa.TEXT(),
                    nullable=True)


def downgrade():
    op.alter_column('c_case', 'language',
                    existing_type=sa.TEXT(),
                    nullable=False)
