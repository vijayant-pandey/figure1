"""Update ActivityRecordType enum

Revision ID: 29de4a2736f3
Revises: b3cef691d9c7
Create Date: 2021-07-13 19:54:31.204305

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '29de4a2736f3'
down_revision = 'b3cef691d9c7'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'activityrecordtype', ['APPROVE', 'COMMENT', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'], ['APPROVE', 'COMMENT', 'DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'])


def downgrade():
    op.sync_enum_values('public', 'activityrecordtype', ['APPROVE', 'COMMENT', 'DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'], ['APPROVE', 'COMMENT', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'])
