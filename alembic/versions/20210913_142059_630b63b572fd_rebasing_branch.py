"""
rebasing branch
Revision ID: 630b63b572fd
Revises: 42f19071c92a, 2d85557e0d18
Create Date: 2021-09-13 14:20:59.846692

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '630b63b572fd'
down_revision = ('42f19071c92a', '2d85557e0d18')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
