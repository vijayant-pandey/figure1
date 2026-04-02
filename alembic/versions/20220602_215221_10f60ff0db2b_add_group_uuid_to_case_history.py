"""Add group_uuid to case history

Revision ID: 10f60ff0db2b
Revises: a07dac5e250a
Create Date: 2022-06-02 21:52:21.167777

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '10f60ff0db2b'
down_revision = 'a07dac5e250a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('h_case_history', sa.Column('group_uuid', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('h_case_history', 'group_uuid')
