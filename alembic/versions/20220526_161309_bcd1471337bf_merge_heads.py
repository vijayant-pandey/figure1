"""merge heads

Revision ID: bcd1471337bf
Revises: 5bed17926356, f81daa076b33
Create Date: 2022-05-26 16:13:09.360257

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bcd1471337bf'
down_revision = ('5bed17926356', 'f81daa076b33')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
