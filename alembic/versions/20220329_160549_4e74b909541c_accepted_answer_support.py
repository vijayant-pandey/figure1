"""Accepted Answer support

Revision ID: 4e74b909541c
Revises: cd4006c7bb6c
Create Date: 2022-03-29 16:05:49.259759

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4e74b909541c'
down_revision = 'cd4006c7bb6c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('c_comment', sa.Column('is_accepted_answer', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('c_comment', 'is_accepted_answer')
