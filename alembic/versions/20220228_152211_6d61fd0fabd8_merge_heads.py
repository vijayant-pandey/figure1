"""merge three heads to one

Revision ID: 6d61fd0fabd8
Revises: 235543f4e7d6, 77784609c4dd, 65788eb83a52
Create Date: 2022-02-28 15:22:11.361435

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6d61fd0fabd8'
down_revision = ('235543f4e7d6', '77784609c4dd', '65788eb83a52')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
