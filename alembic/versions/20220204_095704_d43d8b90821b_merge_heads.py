"""merge heads

Revision ID: d43d8b90821b
Revises: e88ef49f45c7, 61b197dbabbc, 2b82d1a213b4
Create Date: 2022-02-04 09:57:04.695235

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd43d8b90821b'
down_revision = ('e88ef49f45c7', '61b197dbabbc', '2b82d1a213b4')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
