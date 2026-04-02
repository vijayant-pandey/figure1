""" migration merge

Revision ID: 6b1ec2d47c02
Revises: 74a29d99db3f, a4747e02b539
Create Date: 2021-12-13 15:42:27.849621

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '6b1ec2d47c02'
down_revision = ('74a29d99db3f', 'a4747e02b539')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
