"""Rename a_activity_record to n_user_notification

Revision ID: 2b82d1a213b4
Revises: ec508fff0093
Create Date: 2022-01-21 16:34:24.032118

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2b82d1a213b4'
down_revision = 'ec508fff0093'
branch_labels = None
depends_on = None


old_state_enum_name = 'activityrecordstate'
new_state_enum_name = 'usernotificationstate'
old_state_enum = sa.Enum('NEW', 'ACKNOWLEDGED', name=old_state_enum_name)
new_state_enum = sa.Enum('NEW', 'ACKNOWLEDGED', name=new_state_enum_name)

old_type_enum_name = 'activityrecordtype'
new_type_enum_name = 'usernotificationtype'
old_type_enum = sa.Enum('COMMENT', 'REPLY', 'POSTED', 'UPDATED', 'FOLLOW', 'APPROVE', 'REJECT', 'REACT', 'MODERATION_ACTIVITY', 'DELETE', 'CASE_DELETE', 'COMMENT_DELETE', name=old_type_enum_name)
new_type_enum = sa.Enum('APPROVE', 'CASE_DELETE', 'COMMENT', 'COMMENT_DELETE', 'MODERATION_ACTIVITY', 'REACT', 'REJECT', name=new_type_enum_name)


def upgrade():
    # Rename table
    op.rename_table('a_activity_record', 'n_user_notification')

    # Rename columns
    op.alter_column('n_user_notification', 'activity_uuid', new_column_name='notification_uuid')
    op.alter_column('n_user_notification', 'activity_type', new_column_name='notification_type')

    # Rename state enum
    new_state_enum.create(op.get_bind())
    table_name = 'n_user_notification'
    column_name = 'state'
    op.execute(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_state_enum_name} USING {column_name}::text::{new_state_enum_name}')
    op.execute(f'DROP TYPE ' + old_state_enum_name)

    # Rename type enum
    new_type_enum.create(op.get_bind())
    table_name = 'n_user_notification'
    column_name = 'notification_type'
    op.execute(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {new_type_enum_name} USING {column_name}::text::{new_type_enum_name}')
    op.execute(f'DROP TYPE ' + old_type_enum_name)


def downgrade():
    # Rename table
    op.rename_table('n_user_notification', 'a_activity_record')

    # Rename columns
    op.alter_column('a_activity_record', 'notification_uuid', new_column_name='activity_uuid')
    op.alter_column('a_activity_record', 'notification_type', new_column_name='activity_type')

    # Rename state enum
    old_state_enum.create(op.get_bind())
    table_name = 'a_activity_record'
    column_name = 'state'
    op.execute(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {old_state_enum_name} USING {column_name}::text::{old_state_enum_name}')
    op.execute(f'DROP TYPE ' + new_state_enum_name)

    # Rename type enum
    old_type_enum.create(op.get_bind())
    table_name = 'a_activity_record'
    column_name = 'activity_type'
    op.execute(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {old_type_enum_name} USING {column_name}::text::{old_type_enum_name}')
    op.execute(f'DROP TYPE ' + new_type_enum_name)
