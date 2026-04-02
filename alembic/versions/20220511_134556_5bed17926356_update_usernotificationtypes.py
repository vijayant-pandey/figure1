"""Update UserNotificationTypes

Revision ID: 5bed17926356
Revises: 21ff0ee696cf
Create Date: 2022-05-11 13:45:56.750655

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
from figure1.common.utils import update_enum

revision = '5bed17926356'
down_revision = '21ff0ee696cf'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('fk_n_user_notification_group_uuid_g_groups', 'n_user_notification', type_='foreignkey')
    op.create_foreign_key(op.f('fk_n_user_notification_group_uuid_g_groups'), 'n_user_notification', 'g_groups', ['group_uuid'], ['group_uuid'], ondelete='CASCADE')

    update_enum('usernotificationtype',
                ['APPROVE',
                 'CASE_DELETE',
                 'CASE_NOT_DIAGNOSIS_CHOSEN',
                 'COMMENT',
                 'COMMENTED_CASE_DIAGNOSIS',
                 'COMMENT_DELETE',
                 'COMMENT_REPLY',
                 'COMMENT_REPLY_OP',
                 'COMMENT_SAVED_CASE',
                 'COMMENT_SAVED_CASE_OP',
                 'GROUP_INVITE_ACCEPTED',
                 'LIKED_CASE_DIAGNOSIS',
                 'MODERATION_ACTIVITY',
                 'NEW_CASE_FOLLOWED_USER',
                 'NEW_CASE_GROUP',
                 'NEW_CASE_USER_SAVED_CASE',
                 'NEW_FOLLOWER',
                 'PAGING',
                 'PROFESSION_CHANGE_APPROVED',
                 'REACT',
                 'REJECT',
                 'SAVED_CASE_DIAGNOSIS',
                 'SAVED_CASE_UPDATE',
                 ],
                'n_user_notification',
                'notification_type',
                {})


def downgrade():
    op.drop_constraint(op.f('fk_n_user_notification_group_uuid_g_groups'), 'n_user_notification', type_='foreignkey')
    op.create_foreign_key('fk_n_user_notification_group_uuid_g_groups', 'n_user_notification', 'g_groups', ['group_uuid'], ['group_uuid'])

    op.execute("DELETE FROM n_user_notification WHERE notification_type = 'GROUP_INVITE_ACCEPTED'")
    update_enum('usernotificationtype',
                ['APPROVE',
                 'CASE_DELETE',
                 'CASE_NOT_DIAGNOSIS_CHOSEN',
                 'COMMENT',
                 'COMMENTED_CASE_DIAGNOSIS',
                 'COMMENT_DELETE',
                 'COMMENT_REPLY',
                 'COMMENT_REPLY_OP',
                 'COMMENT_SAVED_CASE',
                 'COMMENT_SAVED_CASE_OP',
                 'LIKED_CASE_DIAGNOSIS',
                 'MODERATION_ACTIVITY',
                 'NEW_CASE_FOLLOWED_USER',
                 'NEW_CASE_GROUP',
                 'NEW_CASE_USER_SAVED_CASE',
                 'NEW_FOLLOWER',
                 'PAGING',
                 'PROFESSION_CHANGE_APPROVED',
                 'REACT',
                 'REJECT',
                 'SAVED_CASE_DIAGNOSIS',
                 'SAVED_CASE_UPDATE',
                 ],
                'n_user_notification',
                'notification_type',
                {}
                )
