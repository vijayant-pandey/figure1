"""Add anonymous email subscriber

Revision ID: e8a2d3ffbdd4
Revises: f2f343563f6b
Create Date: 2021-10-12 22:45:12.968466

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e8a2d3ffbdd4'
down_revision = 'f2f343563f6b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('u_anonymous_email_subscriber',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('user_uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=True),
        sa.PrimaryKeyConstraint('email', name=op.f('pk_u_anonymous_email_subscriber'))
    )
    op.create_index(op.f('ix_u_anonymous_email_subscriber_created_at'), 'u_anonymous_email_subscriber', ['created_at'], unique=False)
    op.create_index(op.f('ix_u_anonymous_email_subscriber_deleted_at'), 'u_anonymous_email_subscriber', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_u_anonymous_email_subscriber_email'), 'u_anonymous_email_subscriber', ['email'], unique=False)
    op.create_index(op.f('ix_u_anonymous_email_subscriber_updated_at'), 'u_anonymous_email_subscriber', ['updated_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_u_anonymous_email_subscriber_updated_at'), table_name='u_anonymous_email_subscriber')
    op.drop_index(op.f('ix_u_anonymous_email_subscriber_email'), table_name='u_anonymous_email_subscriber')
    op.drop_index(op.f('ix_u_anonymous_email_subscriber_deleted_at'), table_name='u_anonymous_email_subscriber')
    op.drop_index(op.f('ix_u_anonymous_email_subscriber_created_at'), table_name='u_anonymous_email_subscriber')
    op.drop_table('u_anonymous_email_subscriber')
