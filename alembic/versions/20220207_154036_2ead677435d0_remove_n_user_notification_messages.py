"""Remove n_user_notification messages

Revision ID: 2ead677435d0
Revises: 41c4028a0d6c
Create Date: 2022-02-07 15:40:36.234000

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2ead677435d0'
down_revision = '41c4028a0d6c'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('n_user_notification', 'short_message')
    op.drop_column('n_user_notification', 'long_message')


def downgrade():
    op.add_column('n_user_notification', sa.Column('long_message', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('n_user_notification', sa.Column('short_message', sa.TEXT(), autoincrement=False, nullable=True))
