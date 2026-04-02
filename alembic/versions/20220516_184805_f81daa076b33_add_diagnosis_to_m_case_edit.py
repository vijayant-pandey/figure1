"""Add diagnosis to m_case_edit

Revision ID: f81daa076b33
Revises: fe9d29a7cf7c
Create Date: 2022-05-16 18:48:05.553315

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f81daa076b33'
down_revision = 'fe9d29a7cf7c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('m_case_edit', sa.Column('diagnosis', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('m_case_edit', 'diagnosis')
