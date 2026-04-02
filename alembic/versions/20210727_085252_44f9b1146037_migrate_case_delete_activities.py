"""Migrate case delete activities

Revision ID: 44f9b1146037
Revises: f5c7c7712feb
Create Date: 2021-07-27 08:52:52.623360

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '44f9b1146037'
down_revision = 'f5c7c7712feb'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(f"UPDATE a_activity_record SET activity_type='CASE_DELETE' WHERE activity_type='MODERATION_ACTIVITY'")


def downgrade():
    pass
