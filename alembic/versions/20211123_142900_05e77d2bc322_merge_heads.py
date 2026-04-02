"""Merge heads

Revision ID: 05e77d2bc322
Revises: e5642765723f, 6e68ec993fdb, 3df6de4b7338
Create Date: 2021-11-23 14:29:00.280419

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '05e77d2bc322'
down_revision = ('e5642765723f', '6e68ec993fdb', '3df6de4b7338')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
