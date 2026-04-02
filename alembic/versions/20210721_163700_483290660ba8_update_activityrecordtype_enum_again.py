"""Update ActivityRecordType enum again

Revision ID: 483290660ba8
Revises: 2ec5d74a1c81
Create Date: 2021-07-20 16:37:00.921364

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '483290660ba8'
down_revision = '2ec5d74a1c81'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'activityrecordtype', ['APPROVE', 'COMMENT', 'DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'], ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'])


def downgrade():
    # pass
    op.sync_enum_values('public', 'activityrecordtype', ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'], ['APPROVE', 'COMMENT', 'DELETE', 'FOLLOW', 'MODERATION_ACTIVITY', 'POSTED', 'REACT', 'REJECT', 'REPLY', 'UPDATED'])
