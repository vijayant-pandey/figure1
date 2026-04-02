"""migration_merge

Revision ID: 3bdb43587fae
Revises: a0a595f39ba5, 969d45b0dd70
Create Date: 2022-01-06 21:05:25.402579

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '3bdb43587fae'
down_revision = ('a0a595f39ba5', '969d45b0dd70')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
