"""Ensure comment path index is dropped.

Revision ID: f2f343563f6b
Revises: dda0971c7fe5
Create Date: 2021-10-12 09:26:43.979915

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'f2f343563f6b'
down_revision = 'dda0971c7fe5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""DROP INDEX IF EXISTS ix_comment_path""")


def downgrade():
    pass
