"""Update UserNotificationType enum

Revision ID: 235543f4e7d6
Revises: 2ead677435d0
Create Date: 2022-02-09 16:38:00.083441

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '235543f4e7d6'
down_revision = '2ead677435d0'
branch_labels = None
depends_on = None


def upgrade():
    op.sync_enum_values('public', 'usernotificationtype', ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'MODERATION_ACTIVITY', 'REACT', 'REJECT'], ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'COMMENT_REPLY', 'COMMENT_REPLY_OP', 'COMMENT_SAVED_CASE', 'COMMENT_SAVED_CASE_OP', 'NEW_CASE_FOLLOWED_USER', 'NEW_CASE_USER_SAVED_CASE', 'NEW_FOLLOWER', 'PAGING', 'REACT', 'REJECT', 'SAVED_CASE_UPDATE'])


def downgrade():
    op.sync_enum_values('public', 'usernotificationtype', ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'COMMENT_REPLY', 'COMMENT_REPLY_OP', 'COMMENT_SAVED_CASE', 'COMMENT_SAVED_CASE_OP', 'NEW_CASE_FOLLOWED_USER', 'NEW_CASE_USER_SAVED_CASE', 'NEW_FOLLOWER', 'PAGING', 'REACT', 'REJECT', 'SAVED_CASE_UPDATE'], ['APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'MODERATION_ACTIVITY', 'REACT', 'REJECT'])
