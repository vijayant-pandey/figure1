"""Update iterable state flags

Revision ID: d7db3857f866
Revises: 10c2b19bb908
Create Date: 2021-05-21 13:04:20.287972

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd7db3857f866'
down_revision = '100c648c16ba'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('u_user_state', sa.Column('iterable_unsubscribed', sa.Boolean(), nullable=True))
    op.add_column('u_user_state', sa.Column('unconfirmed_email', sa.Boolean(), nullable=True))
    op.execute("UPDATE u_user_state s SET unconfirmed_email=u.hidden_from_iterable FROM u_user u WHERE u.user_uuid = s.user_uuid")
    op.drop_column('u_user_state', 'hidden_from_iterable')
    op.drop_column('u_user', 'hidden_from_iterable')


def downgrade():
    op.add_column('u_user_state', sa.Column('hidden_from_iterable', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('u_user', sa.Column('hidden_from_iterable', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.execute("UPDATE u_user u SET hidden_from_iterable=s.unconfirmed_email FROM u_user_state s WHERE s.user_uuid = u.user_uuid")
    op.drop_column('u_user_state', 'unconfirmed_email')
    op.drop_column('u_user_state', 'iterable_unsubscribed')
