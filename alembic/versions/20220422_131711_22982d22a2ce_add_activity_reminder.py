"""add activity reminder table

Revision ID: 22982d22a2ce
Revises: 655635605cd0
Create Date: 2022-04-22 13:17:11.363793

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '22982d22a2ce'
down_revision = '655635605cd0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('n_user_activity_reminder',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_sent', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_uuid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['user_uuid'], ['u_user.user_uuid'], name=op.f('fk_n_user_activity_reminder_user_uuid_u_user')),
        sa.PrimaryKeyConstraint('user_uuid', name=op.f('pk_n_user_activity_reminder'))
    )


def downgrade():
    op.drop_table('n_user_activity_reminder')
