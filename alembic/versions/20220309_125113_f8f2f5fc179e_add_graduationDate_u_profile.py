"""add graduation date to user_profile

Revision ID: f8f2f5fc179e
Revises: b909364bc2ac
Create Date: 2022-03-09 12:51:13.042691

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f8f2f5fc179e'
down_revision = 'b909364bc2ac'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('u_profile', sa.Column('graduation_date', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('u_profile', 'graduation_date')
